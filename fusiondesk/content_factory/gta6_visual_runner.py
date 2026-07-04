from pathlib import Path

OUT = Path(
    "flint/projects/ContentFactory/GTA6/concepts/generated_visuals.md"
)

visuals = """
# GTA 6 Visual Plan

Scene 1
- Miami skyline
- GTA style neon
- Luxury cars

Scene 2
- GTA 5 clips comparison
- Creator economy graphics

Scene 3
- RP servers
- Discord communities
- Businesses

Scene 4
- AI generated GTA 6 city concepts

Scene 5
- Money flow graphics
- Gold rush concept
"""

OUT.write_text(visuals)

print("created:", OUT)
