from pathlib import Path

PROMPTS = Path(
    "flint/projects/ContentFactory/GTA6/concepts/asset_prompts.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/media_image_request.md"
)

request = f"""
# Image Generation Request

ENGINE:
Flux / ComfyUI / RunPod

STYLE:
Ultra Realistic
Cinematic
GTA Inspired

PROMPTS:

{PROMPTS.read_text()}
"""

OUT.write_text(request)

print("created:", OUT)
