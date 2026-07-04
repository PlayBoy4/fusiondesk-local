from pathlib import Path
from datetime import datetime

REQUEST = Path(
    "flint/projects/ContentFactory/GTA6/media_image_request.md"
)

OUT_DIR = Path(
    "flint/projects/ContentFactory/GTA6/media/images"
)

OUT_DIR.mkdir(parents=True, exist_ok=True)

job = OUT_DIR / "image_job.md"

job.write_text(f"""
# Image Executor Job

Created:
{datetime.now()}

Provider Priority:

1. Flux
2. ComfyUI
3. RunPod

Input Request:

{REQUEST.read_text()}

Expected Output:

- scene_01.png
- scene_02.png
- scene_03.png
- scene_04.png
- scene_05.png
""")

print("created:", job)

