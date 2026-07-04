from pathlib import Path
from datetime import datetime

REQUEST = Path(
    "flint/projects/ContentFactory/GTA6/media_video_request.md"
)

OUT_DIR = Path(
    "flint/projects/ContentFactory/GTA6/media/video"
)

OUT_DIR.mkdir(parents=True, exist_ok=True)

job = OUT_DIR / "video_job.md"

job.write_text(f"""
# Video Executor Job

Created:
{datetime.now()}

Provider Priority:

1. LTX Video
2. Hyperframes
3. OpenCut
4. Higgs Replacement

Input Request:

{REQUEST.read_text()}

Expected Output:

- short.mp4
- captions.srt
- thumbnail.png
- metadata.json
""")

print("created:", job)
