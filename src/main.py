import os
import re
import json
import logging
import numpy as np
import soundfile as sf
import torch
from typing import Optional, Dict
from kokoro import KPipeline

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

VOICES = {
    "American English": ["af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa"],
    "British English": ["bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"],
    "French": ["ff_siwis"],
    "Italian": ["if_sara", "im_nicola"],
    "Japanese": ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"],
    "Mandarin": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
    "Spanish": ["ef_dora", "em_alex", "em_santa"],
    "Hindi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
    "Portuguese": ["pf_dora", "pm_alex", "pm_santa"]
}


class AudioBookGenerator:
    def __init__(self, voice: str = "af_heart", output_dir: str = "audio", use_gpu: bool = True):
        self.voice = voice
        self.output_dir = output_dir
        
        device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        if device == "cuda":
            logging.info(f"GPU: {torch.cuda.get_device_name(0)}")
        
        self.pipeline = KPipeline(repo_id="hexgrad/Kokoro-82M", lang_code="a", device=device)
        logging.info(f"TTS ready: {voice} on {device}")

    def _synthesize(self, text: str) -> Optional[np.ndarray]:
        try:
            audio_chunks = []
            for _, _, audio in self.pipeline(text, voice=self.voice):
                if isinstance(audio, torch.Tensor):
                    audio = audio.cpu().numpy()
                audio_chunks.append(audio)
            return audio_chunks[0] if audio_chunks else None
        except Exception as e:
            logging.error(f"Synthesis failed: {e}")
            return None

    def process_chapter(self, json_path: str, output_dir: str) -> Dict:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            chapter_id = data.get('chapter_id', 'unknown')
            chunks = data.get('chunks', [])
            output_file = os.path.join(output_dir, f"{chapter_id}.wav")
            
            if os.path.exists(output_file):
                logging.info(f"Skipping {chapter_id} (exists)")
                return {'chapter_id': chapter_id, 'success': len(chunks), 'failed': 0}
            
            logging.info(f"Processing {chapter_id}: {len(chunks)} chunks")
            
            segments, success, failed = [], 0, 0
            for idx, text in enumerate(chunks, 1):
                logging.info(f"  Chunk {idx}/{len(chunks)}")
                audio = self._synthesize(text)
                if audio is not None:
                    segments.append(audio)
                    success += 1
                else:
                    failed += 1
            
            if segments:
                silence = np.zeros(int(24000 * 0.3), dtype=np.float32)
                combined = []
                for i, seg in enumerate(segments):
                    combined.append(seg)
                    if i < len(segments) - 1:
                        combined.append(silence)
                
                final_audio = np.concatenate(combined)
                sf.write(output_file, final_audio, 24000)
                logging.info(f"✓ {chapter_id}.wav ({len(final_audio)/24000:.1f}s)")
            
            return {'chapter_id': chapter_id, 'success': success, 'failed': failed}
        except Exception as e:
            logging.error(f"Failed: {e}")
            return {'error': str(e)}

    def process_novel(self, input_path: str, novel_name: Optional[str] = None) -> Dict:
        if not os.path.exists(input_path):
            return {'error': 'Path not found'}
        
        novel_name = novel_name or os.path.basename(input_path.rstrip('/\\'))
        output_path = os.path.join(self.output_dir, novel_name)
        os.makedirs(output_path, exist_ok=True)
        
        json_files = sorted([f for f in os.listdir(input_path) if f.endswith('.json')])
        if not json_files:
            return {'error': 'No JSON files found'}
        
        logging.info(f"Novel: {novel_name} ({len(json_files)} chapters)")
        
        stats = {'novel': novel_name, 'processed': 0, 'success': 0, 'failed': 0}
        for file in json_files:
            result = self.process_chapter(os.path.join(input_path, file), output_path)
            if 'error' not in result:
                stats['processed'] += 1
                stats['success'] += result.get('success', 0)
                stats['failed'] += result.get('failed', 0)
        
        return stats

    def process_range(self, input_path: str, start: int, end: int, novel_name: Optional[str] = None) -> Dict:
        if not os.path.exists(input_path):
            return {'error': 'Path not found'}
        
        novel_name = novel_name or os.path.basename(input_path.rstrip('/\\'))
        output_path = os.path.join(self.output_dir, novel_name)
        os.makedirs(output_path, exist_ok=True)
        
        all_files = sorted([f for f in os.listdir(input_path) if f.endswith('.json')])
        json_files = []
        for f in all_files:
            match = re.match(r'Chapter_(\d+)\.json', f)
            if match and start <= int(match.group(1)) <= end:
                json_files.append(f)
        
        if not json_files:
            return {'error': f'No chapters in range {start}-{end}'}
        
        logging.info(f"Range: {start}-{end} ({len(json_files)} chapters)")
        
        stats = {'range': f'{start}-{end}', 'processed': 0, 'success': 0, 'failed': 0}
        for file in json_files:
            result = self.process_chapter(os.path.join(input_path, file), output_path)
            if 'error' not in result:
                stats['processed'] += 1
                stats['success'] += result.get('success', 0)
                stats['failed'] += result.get('failed', 0)
        
        return stats


def select_voice() -> str:
    print("\n" + "=" * 70)
    print("VOICE SELECTION".center(70))
    print("=" * 70)
    
    all_voices = []
    for lang, voices in VOICES.items():
        print(f"\n{lang}:")
        for voice in voices:
            idx = len(all_voices) + 1
            print(f"  {idx}. {voice}")
            all_voices.append(voice)
    
    print("=" * 70)
    while True:
        choice = input(f"\nVoice (1-{len(all_voices)} or Enter for default): ").strip()
        if not choice:
            return "af_heart"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_voices):
                return all_voices[idx]
        except ValueError:
            pass
        print("Invalid choice")


def main():
    print("\n" + "=" * 70)
    print("AUDIOBOOK GENERATOR".center(70))
    print("=" * 70)
    print("\n1. Single JSON file\n2. Full novel folder\n3. All novels (Segmentor/output)\n4. Chapter range")
    
    choice = input("\nChoice (1-4): ").strip()
    voice = select_voice()
    use_gpu = input("\nUse GPU? (Y/n): ").strip().lower() != 'n'
    
    gen = AudioBookGenerator(voice=voice, use_gpu=use_gpu)
    
    if choice == "1":
        path = input("JSON file: ").strip()
        name = input("Novel name (optional): ").strip() or None
        stats = gen.process_chapter(path, os.path.join(gen.output_dir, name or "SingleChapter"))
        if 'error' not in stats:
            print(f"\n✓ Complete: {stats['success']} chunks")
    
    elif choice == "2":
        path = input("Novel folder: ").strip()
        name = input("Novel name (optional): ").strip() or None
        stats = gen.process_novel(path, name)
        if 'error' not in stats:
            print(f"\n✓ {stats['novel']}: {stats['processed']} chapters, {stats['success']} chunks")
    
    elif choice == "3":
        base = "Segmentor/output"
        if not os.path.exists(base):
            print("Segmentor/output not found")
            return
        
        folders = [os.path.join(base, d) for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
        for folder in folders:
            stats = gen.process_novel(folder)
            if 'error' not in stats:
                print(f"✓ {stats['novel']}: {stats['success']} chunks")
    
    elif choice == "4":
        path = input("Novel folder: ").strip()
        try:
            start = int(input("Start chapter: "))
            end = int(input("End chapter: "))
            name = input("Novel name (optional): ").strip() or None
            stats = gen.process_range(path, start, end, name)
            if 'error' not in stats:
                print(f"\n✓ Range {stats['range']}: {stats['processed']} chapters, {stats['success']} chunks")
        except ValueError:
            print("Invalid input")
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
