from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "flint" / "projects" / "ContentFactory" / "GTA6" / "shorts" / "generated_ideas.md"

ideas = [
    {
        "title": "How People Will Make Millions From GTA 6",
        "hook": "Everyone thinks GTA 6 is just a game. They are wrong.",
        "pillar": "Economy",
        "score": 95,
    },
    {
        "title": "What GTA 6 Police AI Could Look Like",
        "hook": "GTA 6 police might be smarter than any game we have ever seen.",
        "pillar": "AI Concepts",
        "score": 91,
    },
    {
        "title": "The GTA 6 Server Gold Rush",
        "hook": "The next GTA millionaires might not be players. They might be server owners.",
        "pillar": "Business",
        "score": 94,
    },
]

lines = [
    "# Generated GTA 6 Shorts Ideas",
    "",
    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    "",
]

for i, idea in enumerate(ideas, 1):
    lines += [
        f"## {i}. {idea['title']}",
        "",
        f"Hook: {idea['hook']}",
        f"Pillar: {idea['pillar']}",
        f"Virality Score: {idea['score']}",
        "",
    ]

OUT.write_text("\n".join(lines))
print(f"saved: {OUT}")
