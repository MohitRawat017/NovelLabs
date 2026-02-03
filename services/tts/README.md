# NovelLabs TTS Microservice

Stateless TTS service for Lightning AI deployment.

## What this service does

1. Loads Kokoro TTS model **once** at startup
2. Accepts text + voice + segment_id
3. Generates audio via GPU/CPU inference
4. Uploads to Cloudflare R2
5. Returns CDN-friendly audio URL

```
POST /synthesize
{
  "text": "Hello world",
  "voice": "af_heart",
  "segment_id": "novel_ch1_seg_001"  // opaque string
}

Response:
{
  "audio_url": "https://r2.../audio/novel_ch1_seg_001.wav",
  "duration": 1.5,
  "sample_rate": 24000
}
```

## Local Development

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in R2 credentials
cp .env.example .env

# Run server
python app.py
# or
uvicorn app:app --reload --port 8002
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/voices` | GET | List voices by category |
| `/voices/flat` | GET | List all voices flat |
| `/synthesize` | POST | Generate audio → R2 → URL |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_GPU` | `true` | Toggle GPU/CPU inference |
| `R2_AUDIO_ACCOUNT_ID` | - | Cloudflare account ID |
| `R2_AUDIO_ACCESS_KEY_ID` | - | R2 API key ID |
| `R2_AUDIO_SECRET_ACCESS_KEY` | - | R2 API secret |
| `R2_AUDIO_BUCKET_NAME` | `novellabs-audio` | R2 bucket name |
| `R2_AUDIO_PUBLIC_URL` | - | Custom domain (optional) |

## Lightning AI Deployment

```bash
# Install Lightning CLI
pip install lightning

# Deploy (adjust based on your Lightning setup)
lightning run app app.py --cloud --name novellabs-tts
```

## Notes

- **segment_id is opaque**: This service does not parse or validate segment_id structure
- **No state**: All audio is stored in R2, not locally
- **Model loads once**: Check logs on startup to verify
