from pathlib import Path
from datetime import datetime

REQUEST = Path("flint/projects/ContentFactory/GTA6/media_voice_request.md")
OUT_DIR = Path("flint/projects/ContentFactory/GTA6/media/voice")
OUT_DIR.mkdir(parents=True, exist_ok=True)

voice_job = OUT_DIR / "voice_job.md"

voice_job.write_text(f"""# Voice Executor Job

Created: {datetime.now()}

Provider Priority:
1. VoxCPM2
2. F5-TTS
3. ElevenLabs

Input Request:
{REQUEST.read_text()}

Expected Output:
- voice.mp3
- voice.wav
- subtitles.srt
- timestamps.json
""")

print("created:", voice_job)
