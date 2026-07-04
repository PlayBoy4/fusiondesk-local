from pathlib import Path

SCRIPT = Path(
    "flint/projects/ContentFactory/GTA6/scripts/generated_script.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/media_voice_request.md"
)

request = f"""
# Voice Generation Request

MODEL:
VoxCPM2

VOICE:
Documentary Male

STYLE:
Curiosity
Urgency
Opportunity

SCRIPT:

{SCRIPT.read_text()}
"""

OUT.write_text(request)

print("created:", OUT)
