from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REVIEWS = ROOT / "flint" / "memory" / "trading" / "reviews"
LESSONS = ROOT / "flint" / "memory" / "trading" / "lessons" / "premium_reload_lessons.md"

def extract_lessons(text):
    lessons = []
    capture = False

    for line in text.splitlines():
        if line.startswith("Lessons:"):
            capture = True
            continue

        if capture:
            if line.startswith("TradeMaster Impact"):
                break

            if line.strip().startswith("-"):
                lessons.append(line.strip())

    return lessons


def update_lessons():
    all_lessons = []

    for review in REVIEWS.glob("*.md"):
        all_lessons.extend(
            extract_lessons(review.read_text())
        )

    unique = sorted(set(all_lessons))

    output = [
        "# Premium Reload Lessons",
        ""
    ]

    for i, lesson in enumerate(unique, 1):
        output.append(f"Lesson {i}:")
        output.append(lesson)
        output.append("")

    LESSONS.write_text("\n".join(output))

    print(f"updated {len(unique)} lessons")


if __name__ == "__main__":
    update_lessons()
