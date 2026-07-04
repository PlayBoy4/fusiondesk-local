from pathlib import Path

SCRIPT = Path("flint/projects/ContentFactory/GTA6/scripts/generated_script.md")
OUT = Path("flint/projects/ContentFactory/GTA6/scripts/voice_plan.md")

script = SCRIPT.read_text()

voice = """# GTA 6 Voice Plan

Voice Style:
- Male
- Dramatic
- Documentary
- Confident

Pacing:
- Fast hook
- Medium body
- Slow ending

Emotion:
- Curiosity
- Urgency
- Opportunity

Narration Sections:
"""

for line in script.splitlines():
    if line.strip():
        voice += f"\n- {line[:80]}"

OUT.write_text(voice)
print("created:", OUT)
