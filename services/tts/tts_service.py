import modal
import io

# 1. Define the Environment (No more manual pip installs!)
tts_image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install("kokoro-tts", "soundfile", "pydub", "numpy")
    .apt_install("ffmpeg") # Needed for audio merging
)

app = modal.App("novel-labs-worker", image=tts_image)

# 2. Define the TTS Class (Handles the model "Warm-up")
@app.cls(cpu=2.0, memory=2048) # Kokoro is tiny; 2 CPUs is plenty
class KokoroWorker:
    @modal.enter()
    def setup(self):
        # This runs ONCE when the container starts (Model stays in RAM)
        from kokoro import KPipeline
        self.pipeline = KPipeline(lang_code='a') # English

    @modal.fastapi_endpoint(method="POST")
    def generate_audio(self, data: dict):
        import soundfile as sf
        
        text = data.get("text", "Hello from Modal!")
        voice = data.get("voice", "af_heart")
        
        # Run inference
        generator = self.pipeline(text, voice=voice, speed=1.0)
        
        # For simplicity, we just take the first segment
        # In production, you'd merge segments using pydub
        for _, _, audio in generator:
            buffer = io.BytesIO()
            sf.write(buffer, audio, 24000, format='WAV')
            return buffer.getvalue()