from pathlib import Path

import pytest

from thesegrid.portfolio_review import PortfolioReviewError, load_manual_reviews


def test_load_manual_reviews_validates_and_indexes_rows(tmp_path: Path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "client_site_id,status,reviewer,reviewed_at_utc,notes\n"
        "SITE-A,approved,A. Expert,2026-06-11T12:00:00+00:00,Identity checked\n"
        "SITE-B,rejected,B. Expert,2026-06-11T12:30:00+00:00,Voltage mismatch\n",
        encoding="utf-8",
    )

    reviews = load_manual_reviews(path)

    assert set(reviews) == {"SITE-A", "SITE-B"}
    assert reviews["SITE-A"].status == "approved"
    assert reviews["SITE-A"].reviewer == "A. Expert"
    assert reviews["SITE-B"].notes == "Voltage mismatch"


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            "SITE-A,pending,A. Expert,2026-06-11T12:00:00+00:00,No\n",
            "status",
        ),
        (
            "SITE-A,approved,,2026-06-11T12:00:00+00:00,No reviewer\n",
            "reviewer",
        ),
        (
            "SITE-A,approved,A. Expert,not-a-date,Bad date\n",
            "reviewed_at_utc",
        ),
        (
            "SITE-A,approved,A. Expert,2026-06-11T12:00:00+00:00,First\n"
            "SITE-A,rejected,B. Expert,2026-06-11T13:00:00+00:00,Duplicate\n",
            "duplicate",
        ),
    ],
)
def test_load_manual_reviews_rejects_invalid_contract(
    tmp_path: Path,
    rows: str,
    message: str,
):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "client_site_id,status,reviewer,reviewed_at_utc,notes\n" + rows,
        encoding="utf-8",
    )

    with pytest.raises(PortfolioReviewError, match=message):
        load_manual_reviews(path)
