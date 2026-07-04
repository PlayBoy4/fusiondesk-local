from pathlib import Path
from datetime import datetime

REQUEST = Path(
    "flint/projects/ContentFactory/GTA6/media_voice_request.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/media/voice/vox_job.md"
)

job = f"""
# VoxCPM2 Execution Job

Created:
{datetime.now()}

Provider:
VoxCPM2

Fallback:
F5-TTS

Emergency:
ElevenLabs

Input:

{REQUEST.read_text()}

Expected Output:

voice.mp3
voice.wav
captions.srt
timestamps.json
"""

OUT.write_text(job)

print("created:", OUT)
