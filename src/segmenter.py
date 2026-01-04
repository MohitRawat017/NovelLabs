import os
import json
import re
import logging
from typing import List, Dict
import spacy

# =========================
# CONFIGURATION
# =========================

MAX_CHARS = 250  # XTTS v2: hallucinations occur after ~250-300 chars
MIN_CHARS = 120  # Minimum chars for better prosody
OUTPUT_FORMAT = "json"  # Output format: json

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')


class SmartSegmenter:
    def __init__(self):
        print("[*] Loading lightweight SpaCy sentencizer...")
        
        # We only need sentence boundaries → much faster than full model
        self.nlp = spacy.blank("en")
        self.nlp.add_pipe("sentencizer")

    # --------------------------------------------------

    def _split_long_sentence(self, sentence: str) -> List[str]:
        """
        Fallback splitter for extremely long sentences.
        
        Splits on commas, em dashes, and semicolons to prevent TTS hallucination.
        
        Args:
            sentence: Long sentence to split.
            
        Returns:
            List of smaller text chunks.
        """
        parts = re.split(r'(,|;|—)', sentence)
        chunks = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= MAX_CHARS:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks

    # --------------------------------------------------

    def chunk_text(self, text: str) -> List[str]:
        """
        Sentence-aware, TTS-safe chunking.
        
        Args:
            text: Raw text to chunk.
            
        Returns:
            List of text chunks within MAX_CHARS limit.
        """
        doc = self.nlp(text)
        sentences = [s.text.strip() for s in doc.sents if s.text.strip()]

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # 🚨 Extremely long sentence → fallback split
            if len(sentence) > MAX_CHARS:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                long_parts = self._split_long_sentence(sentence)
                chunks.extend(long_parts)
                continue

            # Normal accumulation
            if len(current_chunk) + len(sentence) + 1 <= MAX_CHARS:
                current_chunk = f"{current_chunk} {sentence}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # --------------------------------------------------

    def process_novel(self, novel_folder: str, output_base_dir: str = "Segmentor/output") -> Dict[str, int]:
        """
        Process all chapters in a novel folder.
        
        Args:
            novel_folder: Path to novel folder containing chapters.
            output_base_dir: Base directory for processed output.
            
        Returns:
            Dictionary with processing statistics.
        """
        novel_name = os.path.basename(novel_folder)
        chapters_dir = novel_folder
        output_dir = os.path.join(output_base_dir, novel_name)

        if not os.path.exists(chapters_dir):
            logging.warning(f"No chapters found in {novel_folder}")
            return {"processed": 0, "total_chunks": 0}

        os.makedirs(output_dir, exist_ok=True)

        files = sorted(f for f in os.listdir(chapters_dir) if f.endswith(".txt"))
        logging.info(f"Processing {len(files)} chapters in {novel_folder}...")
        
        total_chunks = 0
        processed = 0

        for filename in files:
            try:
                with open(os.path.join(chapters_dir, filename), "r", encoding="utf-8") as f:
                    raw_text = f.read()

                # Title + body separation (scraper-aware)
                parts = raw_text.split("\n\n", 1)
                title = parts[0].strip()
                body = parts[1] if len(parts) > 1 else ""

                # Preserve paragraph boundaries
                paragraphs = [p.strip() for p in body.split("\n") if p.strip()]

                chunks = []
                for para in paragraphs:
                    chunks.extend(self.chunk_text(para))

                output_data = {
                    "title": title,
                    "chapter_id": filename.replace(".txt", ""),
                    "chunks": chunks,
                    "chunk_count": len(chunks)
                }

                json_filename = filename.replace(".txt", ".json")
                with open(os.path.join(output_dir, json_filename), "w", encoding="utf-8") as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
                
                total_chunks += len(chunks)
                processed += 1
                logging.info(f"Processed {filename}: {len(chunks)} chunks")
                
            except Exception as e:
                logging.error(f"Failed to process {filename}: {e}")

        logging.info(f"Finished processing {novel_folder}: {processed} chapters, {total_chunks} total chunks")
        return {"processed": processed, "total_chunks": total_chunks}


if __name__ == "__main__":
    segmenter = SmartSegmenter()

    # Input: data/output (from scraper)
    input_base_dir = "data/output"
    if not os.path.exists(input_base_dir):
        logging.error(f"Input folder '{input_base_dir}' not found. Run the scraper first.")
        exit(1)

    # Output: Segmentor/output
    output_base_dir = "Segmentor/output"
    os.makedirs(output_base_dir, exist_ok=True)

    novels = [
        os.path.join(input_base_dir, d)
        for d in os.listdir(input_base_dir)
        if os.path.isdir(os.path.join(input_base_dir, d))
    ]
    
    if not novels:
        logging.error("No novels found in data/output directory.")
        exit(1)

    logging.info(f"Found {len(novels)} novel(s) to process")
    logging.info(f"Output directory: {output_base_dir}\n")
    
    total_stats = {"processed": 0, "total_chunks": 0}
    for novel in novels:
        stats = segmenter.process_novel(novel, output_base_dir)
        total_stats["processed"] += stats["processed"]
        total_stats["total_chunks"] += stats["total_chunks"]
    
    print("\n" + "=" * 60)
    logging.info(f"COMPLETE: {total_stats['processed']} chapters, {total_stats['total_chunks']} total chunks")
    logging.info(f"Saved to: {output_base_dir}")
    print("=" * 60)
