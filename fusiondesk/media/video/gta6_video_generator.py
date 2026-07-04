from pathlib import Path

VOICE = Path(
    "flint/projects/ContentFactory/GTA6/media_voice_request.md"
)

IMAGE = Path(
    "flint/projects/ContentFactory/GTA6/media_image_request.md"
)

VIDEO_PLAN = Path(
    "flint/projects/ContentFactory/GTA6/shorts/video_plan.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/media_video_request.md"
)

request = f"""
# Video Generation Request

ENGINES:
- LTX Video
- Higgs Replacement
- Hyperframes
- OpenCut

STYLE:
Cinematic
Fast paced
High retention
Short-form vertical

VOICE SOURCE:
{VOICE.name}

IMAGE SOURCE:
{IMAGE.name}

VIDEO PLAN:
{VIDEO_PLAN.name}

OUTPUT:
- YouTube Shorts
- TikTok
- Instagram Reels

GOAL:
Create a 30-60 second viral GTA 6 short.
"""

OUT.write_text(request)

print("created:", OUT)
