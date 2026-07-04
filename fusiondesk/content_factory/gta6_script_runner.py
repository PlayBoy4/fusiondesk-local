from pathlib import Path

IDEAS = Path(
    "flint/projects/ContentFactory/GTA6/shorts/generated_ideas.md"
)

OUT = Path(
    "flint/projects/ContentFactory/GTA6/scripts/generated_script.md"
)

script = """
# GTA 6 Gold Rush

HOOK:

Everyone thinks GTA 6 is just another game.

They're wrong.

GTA 6 is about to create an entire economy.

BODY:

When GTA 5 launched, it created:

- YouTubers
- Streamers
- RP servers
- Businesses
- Communities

GTA 6 is expected to be even bigger.

That means:

- content creators
- server owners
- affiliate marketers
- editors
- agencies

all have an opportunity.

ENDING:

The people who get rich from GTA 6 won't necessarily be the best players.

They'll be the people who showed up first.
"""

OUT.write_text(script)

print("created:", OUT)

