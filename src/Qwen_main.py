"""
Qwen3-TTS Local Audiobook Converter
====================================
Converts text documents (TXT, PDF) to audiobooks using Qwen3-TTS models locally.

Models Used:
- CustomVoice: Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice (9 preset voices)
- VoiceClone: Qwen/Qwen3-TTS-12Hz-0.6B-Base (3-second voice cloning)

Author: [Your Name]
Date: 2026-02-01
"""

import os
import shutil
import logging
import hashlib
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import time
import sys
import re
from datetime import datetime

# Core dependencies
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel
import PyPDF2
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# Fix Windows console encoding for emoji/unicode
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# ============================================================================
# CONFIGURATION - UPDATE THESE PATHS AS NEEDED
# ============================================================================

# TODO: Update these directory paths according to your setup
BOOKS_FOLDER = "data/input"          # Input: Place your books here (TXT, PDF)
AUDIOBOOKS_FOLDER = "data/output"    # Output: Generated audiobooks saved here
CHUNKS_TEMP_FOLDER = "data/temp/chunks"  # Temporary chunks during processing
CACHE_FOLDER = "data/cache"          # Cache for processed chunks
LOGS_FOLDER = "logs"                 # Application logs

# Device Configuration
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.bfloat16 if DEVICE == "cuda" else torch.float32

# CustomVoice Settings (1.7B model)
CUSTOM_VOICE_SPEAKER = "Ryan"  # Options: Vivian, Ryan, Logan, Alex, Tiffany, Jake, Keira, Sophia, Chen
CUSTOM_VOICE_LANGUAGE = "English"  # Auto, Chinese, English, Japanese, Korean, etc.
CUSTOM_VOICE_INSTRUCT = "Read in a clear, professional, and confident adult narrator's voice. Speak at a natural, conversational pace - not too fast, not too slow. Maintain a mature, authoritative tone suitable for adult literature."

# VoiceClone Settings (0.6B model)
VOICE_CLONE_LANGUAGE = "English"  # Language of the text to generate

# Processing Settings
CHUNK_SIZE_WORDS = 1500      # Words per chunk (larger = fewer API calls but longer processing)
MAX_WORKERS = 1              # Keep at 1 for sequential processing
AUDIO_FORMAT = "mp3"         # Output format: mp3, wav, etc.
AUDIO_BITRATE = "128k"       # Audio quality
MIN_DELAY_BETWEEN_CHUNKS = 0.1  # Minimal delay for local processing


class Qwen3AudiobookConverter:
    """Local audiobook converter using Qwen3-TTS models"""

    def __init__(self, voice_mode: str = "custom_voice", voice_clone_ref_audio: Optional[str] = None):
        """
        Initialize the converter
        
        Args:
            voice_mode: "custom_voice" (1.7B) or "voice_clone" (0.6B)
            voice_clone_ref_audio: Path to reference audio for voice cloning (required if voice_mode="voice_clone")
        """
        self.voice_mode = voice_mode
        self.voice_clone_ref_audio = voice_clone_ref_audio
        self.voice_clone_ref_text = ""
        
        # Models will be loaded on demand
        self.tts_model = None
        
        self.setup_logging()
        self.setup_directories()
        self.validate_configuration()
        self.load_tts_model()

    def setup_logging(self):
        """Configure logging system"""
        Path(LOGS_FOLDER).mkdir(parents=True, exist_ok=True)
        log_file = Path(LOGS_FOLDER) / f"audiobook_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_directories(self):
        """Create all necessary directories"""
        directories = [
            BOOKS_FOLDER,
            AUDIOBOOKS_FOLDER,
            CHUNKS_TEMP_FOLDER,
            CACHE_FOLDER,
            LOGS_FOLDER
        ]
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Directories created/verified")

    def validate_configuration(self):
        """Validate configuration and requirements"""
        # Check voice mode
        if self.voice_mode not in ["custom_voice", "voice_clone"]:
            print(f"[ERROR] Invalid voice mode: {self.voice_mode}")
            print("Valid modes: 'custom_voice' or 'voice_clone'")
            sys.exit(1)
        
        # For voice cloning, reference audio is required
        if self.voice_mode == "voice_clone":
            if not self.voice_clone_ref_audio:
                print("[ERROR] Voice clone mode requires reference audio!")
                print("Usage: --voice-clone --voice-sample <path>")
                sys.exit(1)
            
            ref_path = Path(self.voice_clone_ref_audio)
            if not ref_path.exists():
                print(f"[ERROR] Reference audio not found: {self.voice_clone_ref_audio}")
                sys.exit(1)
            
            # Validate audio format
            if ref_path.suffix.lower() not in ['.wav', '.mp3', '.flac']:
                print(f"[WARNING] Reference audio format {ref_path.suffix} may not be optimal")
                print("Recommended format: .wav")
        
        # Check CUDA availability
        if DEVICE == "cuda":
            print(f"[OK] CUDA available - GPU: {torch.cuda.get_device_name(0)}")
            print(f"[OK] VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            print("[WARNING] CUDA not available - using CPU (will be slower)")

    def load_tts_model(self):
        """Load the appropriate Qwen3-TTS model based on voice mode"""
        try:
            self.logger.info(f"Loading Qwen3-TTS model for {self.voice_mode} mode...")
            print(f"[INFO] Loading Qwen3-TTS model ({self.voice_mode})...")
            print(f"[INFO] Device: {DEVICE}, Dtype: {DTYPE}")
            
            if self.voice_mode == "custom_voice":
                # Load 1.7B CustomVoice model
                model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
                self.logger.info(f"Loading model: {model_name}")
                
                self.tts_model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map="auto" if DEVICE == "cuda" else None,
                    dtype=DTYPE,
                    attn_implementation="flash_attention_2" if DEVICE == "cuda" else "eager"
                )
                
                print(f"[OK] Loaded CustomVoice model (1.7B)")
                print(f"[INFO] Speaker: {CUSTOM_VOICE_SPEAKER}")
                print(f"[INFO] Language: {CUSTOM_VOICE_LANGUAGE}")
                
                # Display available speakers
                try:
                    speakers = self.tts_model.get_supported_speakers()
                    languages = self.tts_model.get_supported_languages()
                    self.logger.info(f"Available speakers: {speakers}")
                    self.logger.info(f"Supported languages: {languages}")
                except Exception as e:
                    self.logger.warning(f"Could not retrieve speaker/language info: {e}")
            
            elif self.voice_mode == "voice_clone":
                # Load 0.6B Base model for voice cloning
                model_name = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
                self.logger.info(f"Loading model: {model_name}")
                
                self.tts_model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map="auto" if DEVICE == "cuda" else None,
                    dtype=DTYPE,
                    attn_implementation="flash_attention_2" if DEVICE == "cuda" else "eager"
                )
                
                print(f"[OK] Loaded Base model for voice cloning (0.6B)")
                print(f"[INFO] Reference audio: {Path(self.voice_clone_ref_audio).name}")
                
                # Transcribe reference audio
                print("[INFO] Preparing reference audio for voice cloning...")
                self.voice_clone_ref_text = self._transcribe_reference_audio()
                print(f"[OK] Reference transcription: {self.voice_clone_ref_text[:100]}...")
            
            self.logger.info("TTS model loaded successfully")
            
        except Exception as e:
            print(f"[ERROR] Failed to load TTS model!")
            print(f"Error: {e}")
            print("\nTroubleshooting:")
            print("1. Ensure qwen-tts is installed: pip install -U qwen-tts")
            print("2. Model will be downloaded automatically on first use")
            print("3. Ensure sufficient disk space (~5GB for 1.7B, ~3GB for 0.6B)")
            print("4. Check internet connection for model download")
            import traceback
            self.logger.error(traceback.format_exc())
            sys.exit(1)

    def _transcribe_reference_audio(self) -> str:
        """
        Transcribe reference audio for voice cloning
        
        Note: For production use, you should provide the reference text manually
        or use a proper ASR model. This is a placeholder.
        """
        # TODO: Implement proper transcription using Whisper or similar
        # For now, user must provide reference text manually or via ASR
        
        # Option 1: Ask user to provide text
        print("\n" + "="*70)
        print("REFERENCE AUDIO TRANSCRIPTION REQUIRED")
        print("="*70)
        print(f"Reference audio: {self.voice_clone_ref_audio}")
        print("\nPlease provide the transcription of the reference audio.")
        print("This is what the speaker says in the reference audio.")
        print("Accurate transcription improves voice cloning quality.\n")
        
        ref_text = input("Enter transcription: ").strip()
        
        if not ref_text:
            print("[ERROR] Transcription cannot be empty!")
            sys.exit(1)
        
        return ref_text
        
        # Option 2: Use automatic transcription (requires additional setup)
        # try:
        #     from faster_whisper import WhisperModel
        #     model = WhisperModel("small", device=DEVICE)
        #     segments, info = model.transcribe(self.voice_clone_ref_audio)
        #     ref_text = " ".join([segment.text for segment in segments])
        #     return ref_text.strip()
        # except ImportError:
        #     print("[ERROR] faster-whisper not installed for auto-transcription")
        #     print("Install with: pip install faster-whisper")
        #     sys.exit(1)

    def generate_audio_chunk(self, text: str, chunk_num: int) -> Optional[str]:
        """
        Generate audio for a text chunk using Qwen3-TTS
        
        Args:
            text: Text content to convert to speech
            chunk_num: Chunk number for identification
            
        Returns:
            Path to generated audio file or None on failure
        """
        try:
            # Check cache first
            cache_path = self._get_cache_path(text)
            if cache_path.exists():
                output_path = Path(CHUNKS_TEMP_FOLDER) / f"chunk_{chunk_num:04d}.wav"
                shutil.copy2(cache_path, output_path)
                self.logger.debug(f"Using cached audio for chunk {chunk_num}")
                return str(output_path)
            
            self.logger.info(f"Generating audio for chunk {chunk_num}")
            
            # Generate audio based on mode
            if self.voice_mode == "custom_voice":
                wavs, sr = self.tts_model.generate_custom_voice(
                    text=text,
                    language=CUSTOM_VOICE_LANGUAGE,
                    speaker=CUSTOM_VOICE_SPEAKER,
                    instruct=CUSTOM_VOICE_INSTRUCT
                )
            
            elif self.voice_mode == "voice_clone":
                wavs, sr = self.tts_model.generate_voice_clone(
                    text=text,
                    language=VOICE_CLONE_LANGUAGE,
                    ref_audio=self.voice_clone_ref_audio,
                    ref_text=self.voice_clone_ref_text
                )
            
            # Save generated audio
            output_path = Path(CHUNKS_TEMP_FOLDER) / f"chunk_{chunk_num:04d}.wav"
            sf.write(str(output_path), wavs[0], sr)
            
            # Cache the result
            sf.write(str(cache_path), wavs[0], sr)
            
            self.logger.debug(f"Chunk {chunk_num} generated successfully")
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"Failed to generate chunk {chunk_num}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def process_chunk_with_retry(self, args: Tuple[int, str], max_retries: int = 3) -> bool:
        """
        Process a chunk with retry logic
        
        Args:
            args: Tuple of (chunk_num, text)
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        chunk_num, text = args
        
        # Small delay between chunks to avoid memory issues
        if chunk_num > 1:
            time.sleep(MIN_DELAY_BETWEEN_CHUNKS)
        
        for attempt in range(max_retries):
            try:
                result = self.generate_audio_chunk(text, chunk_num)
                if result and Path(result).exists():
                    return True
                else:
                    self.logger.warning(f"Chunk {chunk_num} attempt {attempt + 1} failed - no output")
            except Exception as e:
                self.logger.warning(f"Chunk {chunk_num} attempt {attempt + 1} error: {e}")
            
            # Retry with exponential backoff
            if attempt < max_retries - 1:
                sleep_time = 1 * (2 ** attempt)  # 1s, 2s, 4s
                self.logger.info(f"Retrying chunk {chunk_num} in {sleep_time}s...")
                time.sleep(sleep_time)
        
        self.logger.error(f"Chunk {chunk_num} failed after {max_retries} attempts")
        return False

    def _get_cache_path(self, text: str) -> Path:
        """Generate cache file path for a text chunk"""
        # Create hash of text + voice settings
        if self.voice_mode == "custom_voice":
            content = f"{text}_custom_{CUSTOM_VOICE_SPEAKER}_{CUSTOM_VOICE_LANGUAGE}"
        else:
            ref_name = Path(self.voice_clone_ref_audio).name if self.voice_clone_ref_audio else "unknown"
            content = f"{text}_clone_{ref_name}"
        
        hash_obj = hashlib.md5(content.encode('utf-8'))
        cache_file = Path(CACHE_FOLDER) / f"{hash_obj.hexdigest()}.wav"
        return cache_file

    # ========================================================================
    # TEXT EXTRACTION
    # ========================================================================

    def extract_text_from_file(self, file_path: Path) -> str:
        """Extract text from supported file formats"""
        extension = file_path.suffix.lower()
        
        self.logger.info(f"Extracting text from {file_path.name} ({extension})")
        
        if extension == '.txt':
            return self._extract_from_txt(file_path)
        elif extension == '.pdf':
            return self._extract_from_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file format: {extension}")

    def _extract_from_txt(self, file_path: Path) -> str:
        """Extract text from TXT file with encoding detection"""
        encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
                self.logger.info(f"Successfully read TXT with {encoding} encoding")
                return self._clean_text(text)
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"Could not decode {file_path.name} with any known encoding")

    def _extract_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file"""
        text_parts = []
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                self.logger.info(f"PDF contains {total_pages} pages")
                print(f"[INFO] Extracting text from {total_pages} pages...")
                
                for page_num in range(total_pages):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        
                        if page_text and page_text.strip():
                            text_parts.append(page_text)
                        
                        # Progress update every 10 pages
                        if (page_num + 1) % 10 == 0:
                            print(f"[INFO] Extracted {page_num + 1}/{total_pages} pages")
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to extract page {page_num + 1}: {e}")
                        continue
                
                full_text = "\n\n".join(text_parts)
                self.logger.info(f"Extracted {len(full_text)} characters from PDF")
                return self._clean_text(full_text)
                
        except Exception as e:
            self.logger.error(f"PDF extraction failed: {e}")
            raise

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove standalone page numbers
        text = re.sub(r'\b\d{1,3}\b(?=\s|$)', '', text)
        
        # Remove excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    # ========================================================================
    # TEXT CHUNKING
    # ========================================================================

    def split_into_chunks(self, text: str) -> List[str]:
        """
        Split text into manageable chunks for TTS processing
        
        Args:
            text: Full text to split
            
        Returns:
            List of text chunks
        """
        if not text.strip():
            return []
        
        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        current_words = 0
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            
            # If sentence itself is too long, split further
            if sentence_words > CHUNK_SIZE_WORDS:
                # Save current chunk if exists
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_words = 0
                
                # Split long sentence by punctuation
                parts = re.split(r'[,;:]', sentence)
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    
                    part_words = len(part.split())
                    
                    if current_words + part_words <= CHUNK_SIZE_WORDS:
                        current_chunk += part + " "
                        current_words += part_words
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = part + " "
                        current_words = part_words
            else:
                # Add sentence to current chunk if it fits
                if current_words + sentence_words <= CHUNK_SIZE_WORDS:
                    current_chunk += sentence + " "
                    current_words += sentence_words
                else:
                    # Save current chunk and start new one
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + " "
                    current_words = sentence_words
        
        # Add remaining chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Filter out empty chunks
        chunks = [chunk for chunk in chunks if chunk.strip()]
        
        self.logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

    # ========================================================================
    # AUDIO COMBINATION
    # ========================================================================

    def combine_audio_chunks(self, total_chunks: int, output_path: Path, 
                           results: Optional[Dict[int, bool]] = None) -> bool:
        """
        Combine individual audio chunks into final audiobook
        
        Args:
            total_chunks: Total number of chunks
            output_path: Path for final audiobook
            results: Dictionary tracking which chunks succeeded
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print("\n[INFO] Combining audio chunks...")
            combined = AudioSegment.empty()
            successful = 0
            missing_chunks = []
            
            for i in range(1, total_chunks + 1):
                # Skip failed chunks if we're tracking results
                if results is not None and not results.get(i, False):
                    missing_chunks.append(i)
                    continue
                
                chunk_file = Path(CHUNKS_TEMP_FOLDER) / f"chunk_{i:04d}.wav"
                
                if chunk_file.exists():
                    try:
                        chunk_audio = AudioSegment.from_wav(str(chunk_file))
                        combined += chunk_audio
                        successful += 1
                        
                        if successful % 10 == 0:
                            print(f"[INFO] Combined {successful}/{total_chunks} chunks")
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to load chunk {i}: {e}")
                        missing_chunks.append(i)
                else:
                    self.logger.warning(f"Chunk file not found: {chunk_file}")
                    missing_chunks.append(i)
            
            if successful == 0:
                raise RuntimeError("No valid audio chunks found to combine")
            
            # Export final audiobook
            print(f"[INFO] Exporting audiobook to {AUDIO_FORMAT.upper()}...")
            combined.export(
                str(output_path),
                format=AUDIO_FORMAT,
                bitrate=AUDIO_BITRATE
            )
            
            duration_minutes = len(combined) / 1000 / 60
            self.logger.info(
                f"Audiobook created: {output_path} "
                f"({successful}/{total_chunks} chunks, {duration_minutes:.1f} minutes)"
            )
            
            print(f"[OK] Audiobook saved: {output_path.name}")
            print(f"[INFO] Duration: {duration_minutes:.1f} minutes")
            print(f"[INFO] Chunks: {successful}/{total_chunks}")
            
            if missing_chunks:
                print(f"[WARNING] Missing chunks: {missing_chunks}")
                self.logger.warning(f"Missing chunks: {missing_chunks}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to combine audio chunks: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    def cleanup_temp_files(self):
        """Remove temporary chunk files"""
        try:
            chunk_count = 0
            chunk_dir = Path(CHUNKS_TEMP_FOLDER)
            
            if chunk_dir.exists():
                for chunk_file in chunk_dir.glob("chunk_*.wav"):
                    try:
                        chunk_file.unlink()
                        chunk_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to delete {chunk_file}: {e}")
            
            if chunk_count > 0:
                self.logger.info(f"Cleaned up {chunk_count} temporary chunk files")
                print(f"[INFO] Cleaned up {chunk_count} temporary files")
                
        except Exception as e:
            self.logger.warning(f"Cleanup failed: {e}")

    # ========================================================================
    # MAIN CONVERSION PROCESS
    # ========================================================================

    def convert_book(self, file_path: Path) -> bool:
        """
        Convert a single book to audiobook
        
        Args:
            file_path: Path to book file (TXT or PDF)
            
        Returns:
            True if conversion successful, False otherwise
        """
        self.logger.info(f"Starting conversion: {file_path.name}")
        print(f"\n{'='*70}")
        print(f"CONVERTING: {file_path.name}")
        print(f"{'='*70}")
        
        start_time = time.time()
        
        try:
            # Step 1: Extract text
            print("[1/4] Extracting text...")
            text = self.extract_text_from_file(file_path)
            
            if not text.strip():
                self.logger.error("No text extracted from file")
                print("[ERROR] No text could be extracted from the file")
                return False
            
            word_count = len(text.split())
            print(f"[OK] Extracted {len(text)} characters ({word_count} words)")
            
            # Step 2: Split into chunks
            print("[2/4] Splitting into chunks...")
            chunks = self.split_into_chunks(text)
            total_chunks = len(chunks)
            
            if total_chunks == 0:
                self.logger.error("No chunks created from text")
                print("[ERROR] Could not create chunks from text")
                return False
            
            chunk_sizes = [len(chunk.split()) for chunk in chunks]
            avg_chunk_size = sum(chunk_sizes) / len(chunk_sizes)
            
            print(f"[OK] Created {total_chunks} chunks (avg {avg_chunk_size:.0f} words/chunk)")
            
            # Estimate processing time
            est_minutes = total_chunks * 0.3  # ~30 seconds per chunk
            print(f"[INFO] Estimated processing time: ~{est_minutes:.1f} minutes")
            
            # Step 3: Generate audio for each chunk
            print(f"[3/4] Generating audio ({total_chunks} chunks)...")
            print(f"{'='*70}")
            
            chunk_args = [(i + 1, chunk) for i, chunk in enumerate(chunks)]
            results = {}
            
            for chunk_num, chunk_text in chunk_args:
                try:
                    result = self.process_chunk_with_retry((chunk_num, chunk_text))
                    results[chunk_num] = result
                    
                    if result:
                        print(f"[OK] Chunk {chunk_num:3d}/{total_chunks} ✓")
                    else:
                        print(f"[FAIL] Chunk {chunk_num:3d}/{total_chunks} ✗")
                        
                except Exception as e:
                    results[chunk_num] = False
                    print(f"[ERROR] Chunk {chunk_num:3d}/{total_chunks} - {str(e)[:50]}")
            
            successful_chunks = sum(1 for v in results.values() if v)
            
            print(f"{'='*70}")
            print(f"Chunk processing complete: {successful_chunks}/{total_chunks} successful")
            
            if successful_chunks == 0:
                self.logger.error("No chunks were successfully processed")
                print("[ERROR] All chunks failed to process")
                self.cleanup_temp_files()
                return False
            
            if successful_chunks < total_chunks:
                print(f"[WARNING] Only {successful_chunks}/{total_chunks} chunks succeeded")
                print("[INFO] Proceeding with partial audiobook...")
            
            # Step 4: Combine chunks
            print(f"[4/4] Combining audio chunks...")
            output_path = Path(AUDIOBOOKS_FOLDER) / f"{file_path.stem}.{AUDIO_FORMAT}"
            success = self.combine_audio_chunks(total_chunks, output_path, results)
            
            if success:
                duration = time.time() - start_time
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                
                print(f"\n{'='*70}")
                print(f"CONVERSION SUCCESSFUL")
                print(f"{'='*70}")
                print(f"Output: {output_path}")
                print(f"Time: {minutes}m {seconds}s")
                print(f"{'='*70}\n")
                
                self.logger.info(f"Conversion completed in {minutes}m {seconds}s")
            else:
                print("[ERROR] Failed to combine audio chunks")
            
            # Cleanup
            self.cleanup_temp_files()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Conversion failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            print(f"[ERROR] Conversion failed: {e}")
            self.cleanup_temp_files()
            return False

    def run(self):
        """Main entry point - convert all books in input folder"""
        print("\n" + "="*70)
        print("QWEN3-TTS AUDIOBOOK CONVERTER (LOCAL)")
        print("="*70)
        print(f"Input folder:  {BOOKS_FOLDER}")
        print(f"Output folder: {AUDIOBOOKS_FOLDER}")
        print(f"Device:        {DEVICE}")
        print(f"Voice mode:    {self.voice_mode}")
        
        if self.voice_mode == "custom_voice":
            print(f"Speaker:       {CUSTOM_VOICE_SPEAKER}")
            print(f"Language:      {CUSTOM_VOICE_LANGUAGE}")
        else:
            print(f"Reference:     {Path(self.voice_clone_ref_audio).name}")
            print(f"Language:      {VOICE_CLONE_LANGUAGE}")
        
        print(f"Output format: {AUDIO_FORMAT.upper()}")
        print("="*70 + "\n")
        
        # Find books to convert
        books_dir = Path(BOOKS_FOLDER)
        supported_formats = ['.txt', '.pdf']
        
        book_files = [
            f for f in books_dir.iterdir()
            if f.is_file() and f.suffix.lower() in supported_formats
        ]
        
        if not book_files:
            print(f"[INFO] No books found in {BOOKS_FOLDER}")
            print(f"Supported formats: {', '.join(supported_formats)}")
            
            # Create sample file
            sample_file = books_dir / "sample.txt"
            sample_content = (
                "This is a sample audiobook for testing the Qwen3-TTS converter. "
                "The system will convert this text to speech using local models. "
                "You can replace this file with your own books to convert them to audiobooks."
            )
            with open(sample_file, 'w', encoding='utf-8') as f:
                f.write(sample_content)
            
            print(f"[INFO] Created sample file: {sample_file}")
            print("[INFO] Add your own books and run again")
            return
        
        print(f"[INFO] Found {len(book_files)} book(s) to convert\n")
        
        # Convert each book
        results = {}
        
        for idx, book_file in enumerate(book_files, 1):
            print(f"Book {idx}/{len(book_files)}")
            
            try:
                success = self.convert_book(book_file)
                results[book_file.name] = success
                
            except KeyboardInterrupt:
                print("\n[WARNING] Conversion interrupted by user")
                break
                
            except Exception as e:
                self.logger.error(f"Unexpected error processing {book_file.name}: {e}")
                results[book_file.name] = False
        
        # Print summary
        successful = sum(results.values())
        total = len(results)
        
        print("\n" + "="*70)
        print("CONVERSION SUMMARY")
        print("="*70)
        print(f"Total:      {total}")
        print(f"Successful: {successful}")
        print(f"Failed:     {total - successful}")
        print("="*70)
        
        for filename, success in results.items():
            status = "[OK]  " if success else "[FAIL]"
            print(f"{status} {filename}")
        
        print("="*70)
        
        if successful > 0:
            print(f"\n[OK] Audiobooks saved to: {AUDIOBOOKS_FOLDER}/\n")


def main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(
        description="Convert books to audiobooks using Qwen3-TTS (local inference)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use custom voice with preset speaker (1.7B model)
  python qwen3_audiobook_converter.py
  
  # Use voice cloning with reference audio (0.6B model)
  python qwen3_audiobook_converter.py --voice-clone --voice-sample reference.wav
  
Supported formats:
  - Text files (.txt)
  - PDF files (.pdf)
  
Requirements:
  - qwen-tts: pip install -U qwen-tts
  - PyPDF2: pip install PyPDF2
  - pydub: pip install pydub
  - soundfile: pip install soundfile
        """
    )
    
    parser.add_argument(
        "--voice-clone",
        action="store_true",
        help="Use voice cloning mode (requires --voice-sample)"
    )
    
    parser.add_argument(
        "--voice-sample",
        type=str,
        help="Path to reference audio for voice cloning (WAV recommended, 3+ seconds)"
    )
    
    args = parser.parse_args()
    
    # Validate dependencies
    try:
        import torch
        import soundfile
        from qwen_tts import Qwen3TTSModel
    except ImportError as e:
        print("[ERROR] Missing required dependencies!")
        print("\nInstall with:")
        print("  pip install -U qwen-tts torch soundfile PyPDF2 pydub")
        print(f"\nDetails: {e}")
        sys.exit(1)
    
    # Determine voice mode
    if args.voice_clone:
        if not args.voice_sample:
            print("[ERROR] --voice-clone requires --voice-sample")
            print("Usage: python qwen3_audiobook_converter.py --voice-clone --voice-sample <path>")
            sys.exit(1)
        voice_mode = "voice_clone"
        voice_clone_ref_audio = args.voice_sample
    else:
        voice_mode = "custom_voice"
        voice_clone_ref_audio = None
    
    # Run converter
    try:
        converter = Qwen3AudiobookConverter(
            voice_mode=voice_mode,
            voice_clone_ref_audio=voice_clone_ref_audio
        )
        converter.run()
        
    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested by user")
        
    except Exception as e:
        print(f"[FATAL] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()