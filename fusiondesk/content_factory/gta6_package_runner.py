from pathlib import Path
from datetime import datetime

ROOT = Path("flint/projects/ContentFactory/GTA6")

OUT = ROOT / "production_package.md"

files = [
    ROOT / "shorts" / "generated_ideas.md",
    ROOT / "scripts" / "generated_script.md",
    ROOT / "scripts" / "voice_plan.md",
    ROOT / "concepts" / "generated_visuals.md",
    ROOT / "shorts" / "video_plan.md",
    ROOT / "shorts" / "thumbnail_plan.md",
    ROOT / "concepts" / "asset_prompts.md",
]

package = []
package.append("# FusionDesk GTA6 Production Package")
package.append("")
package.append(f"Generated: {datetime.now()}")
package.append("")

for f in files:
    package.append("")
    package.append("=" * 60)
    package.append(f"# {f.name}")
    package.append("=" * 60)
    package.append("")

    if f.exists():
        package.append(f.read_text())
    else:
        package.append("MISSING FILE")

OUT.write_text("\n".join(package))

print("created:", OUT)
