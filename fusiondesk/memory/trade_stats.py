from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REVIEWS = ROOT / "flint" / "memory" / "trading" / "reviews"
STATS = ROOT / "flint" / "memory" / "trading" / "stats.md"

def field(text, name):
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""

def main():
    reviews = list(REVIEWS.glob("*.md"))
    total = len(reviews)

    tickers = {}
    grades = {}
    lessons = {}

    for path in reviews:
        text = path.read_text()
        ticker = field(text, "Ticker") or "Unknown"
        execution = field(text, "Execution Grade") or "Unknown"

        tickers[ticker] = tickers.get(ticker, 0) + 1
        grades[execution] = grades.get(execution, 0) + 1

        for line in text.splitlines():
            if line.strip().startswith("-"):
                lesson = line.strip()
                lessons[lesson] = lessons.get(lesson, 0) + 1

    out = ["# TradeMaster Stats", "", f"Total Reviews: {total}", ""]

    out.append("## Tickers")
    for k, v in sorted(tickers.items()):
        out.append(f"- {k}: {v}")

    out += ["", "## Execution Grades"]
    for k, v in sorted(grades.items()):
        out.append(f"- {k}: {v}")

    out += ["", "## Repeated Lessons"]
    for k, v in sorted(lessons.items(), key=lambda x: (-x[1], x[0])):
        out.append(f"- {k} ({v})")

    STATS.write_text("\n".join(out) + "\n")
    print(f"stats updated: {STATS}")

if __name__ == "__main__":
    main()
