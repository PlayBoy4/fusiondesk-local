from pathlib import Path

SCRIPT = Path(
    "flint/projects/ContentFactory/GTA6/scripts/generated_script.md"
)

VOICE = Path(
    "flint/projects/ContentFactory/GTA6/scripts/voice_plan.md"
)

VISUALS = Path(
    "flint/projects/ContentFactory/GTA6/concepts/generated_visuals.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/shorts/video_plan.md"
)

plan = f"""
# GTA 6 Video Production Plan

INPUTS

Script:
{SCRIPT.name}

Voice:
{VOICE.name}

Visuals:
{VISUALS.name}

---

SHOT 1
Duration: 3 sec
Visual:
- Miami skyline
Narration:
- Everyone thinks GTA 6 is just another game.

SHOT 2
Duration: 4 sec
Visual:
- GTA 5 creator economy montage
Narration:
- They're wrong.

SHOT 3
Duration: 5 sec
Visual:
- Money flow animation
Narration:
- GTA 6 is about to create an entire economy.

SHOT 4
Duration: 8 sec
Visual:
- RP servers
- Streamers
- Businesses
Narration:
- GTA 5 created entire industries.

SHOT 5
Duration: 6 sec
Visual:
- GTA 6 AI concept footage
Narration:
- GTA 6 may become even bigger.

ENDING
Visual:
- Gold rush graphics
Narration:
- The winners will be the people who showed up first.
"""

OUT.write_text(plan)

print("created:", OUT)
