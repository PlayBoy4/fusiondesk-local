from pathlib import Path
from datetime import datetime
import re

ROOT = Path(__file__).resolve().parents[2]
REVIEWS_DIR = ROOT / "flint" / "memory" / "trading" / "reviews"
LESSONS_FILE = ROOT / "flint" / "memory" / "trading" / "lessons" / "premium_reload_lessons.md"

def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-")

def write_trade_review(
    ticker: str,
    direction: str,
    entry: str,
    exit: str,
    thesis_grade: str,
    entry_grade: str,
    execution_grade: str,
    risk_grade: str,
    lessons: list[str],
    impact: list[str],
):
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date}-{slug(ticker)}-trade-review.md"
    path = REVIEWS_DIR / filename

    content = [
        "# Trade Review Memory",
        "",
        f"Date: {date}",
        "",
        f"Ticker: {ticker}",
        "",
        f"Direction: {direction}",
        "",
        f"Entry: {entry}",
        "",
        f"Exit: {exit}",
        "",
        f"Thesis Grade: {thesis_grade}",
        "",
        f"Entry Grade: {entry_grade}",
        "",
        f"Execution Grade: {execution_grade}",
        "",
        f"Risk Grade: {risk_grade}",
        "",
        "Lessons:",
        *[f"- {x}" for x in lessons],
        "",
        "Memory Update: YES",
        "",
        "TradeMaster Impact:",
        *[f"- {x}" for x in impact],
        "",
    ]

    path.write_text("\n".join(content))
    return path

if __name__ == "__main__":
    saved = write_trade_review(
        ticker="IWM",
        direction="Bullish",
        entry="0.24",
        exit="0.40",
        thesis_grade="A",
        entry_grade="A",
        execution_grade="B",
        risk_grade="A",
        lessons=[
            "Premium floor held.",
            "Second retest worked.",
            "Exited too early."
        ],
        impact=[
            "Scale out.",
            "Leave runner contracts."
        ],
    )
    print(f"saved: {saved}")
