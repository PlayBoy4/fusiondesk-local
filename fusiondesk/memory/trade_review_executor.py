from trade_memory_writer import write_trade_review
from lesson_updater import update_lessons
from trade_stats import main as update_stats

def review_trade(
    ticker,
    direction,
    entry,
    exit,
    thesis,
    notes,
):
    print("=== TRADE REVIEW ===")

    thesis_grade = "A"
    entry_grade = "A"
    execution_grade = "B"
    risk_grade = "A"

    lessons = [
        "Premium floor held.",
        "Second retest worked.",
        "Exited too early."
    ]

    impact = [
        "Scale out.",
        "Leave runner contracts."
    ]

    review = write_trade_review(
        ticker=ticker,
        direction=direction,
        entry=entry,
        exit=exit,
        thesis_grade=thesis_grade,
        entry_grade=entry_grade,
        execution_grade=execution_grade,
        risk_grade=risk_grade,
        lessons=lessons,
        impact=impact,
    )

    print(f"review saved: {review}")

    update_lessons()
    print("lessons updated")

    update_stats()
    print("stats updated")

    return review


if __name__ == "__main__":
    review_trade(
        ticker="IWM",
        direction="Bullish",
        entry="0.24",
        exit="0.40",
        thesis="""
        Daily bullish
        4H bullish
        1H bullish
        Premium reload
        Second retest
        """,
        notes="""
        Took profit too early.
        Trade later extended.
        """
    )
