from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


ManualReviewDecision = Literal["approved", "rejected"]

REQUIRED_COLUMNS = (
    "client_site_id",
    "status",
    "reviewer",
    "reviewed_at_utc",
    "notes",
)


class PortfolioReviewError(ValueError):
    pass


@dataclass(frozen=True)
class ManualReview:
    client_site_id: str
    status: ManualReviewDecision
    reviewer: str
    reviewed_at_utc: str
    notes: str


def load_manual_reviews(path: Path) -> dict[str, ManualReview]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [
                column
                for column in REQUIRED_COLUMNS
                if column not in (reader.fieldnames or ())
            ]
            if missing:
                raise PortfolioReviewError(
                    f"{path} missing columns: {', '.join(missing)}"
                )
            rows = list(reader)
    except OSError as exc:
        raise PortfolioReviewError(f"cannot read manual reviews {path}: {exc}") from exc

    reviews: dict[str, ManualReview] = {}
    for row_number, row in enumerate(rows, start=2):
        client_site_id = str(row["client_site_id"]).strip()
        status = str(row["status"]).strip().lower()
        reviewer = str(row["reviewer"]).strip()
        reviewed_at = str(row["reviewed_at_utc"]).strip()
        notes = str(row["notes"]).strip()
        if not client_site_id:
            raise PortfolioReviewError(
                f"{path} row {row_number}: client_site_id is required"
            )
        if client_site_id in reviews:
            raise PortfolioReviewError(
                f"{path} row {row_number}: duplicate client_site_id {client_site_id}"
            )
        if status not in {"approved", "rejected"}:
            raise PortfolioReviewError(
                f"{path} row {row_number}: status must be approved or rejected"
            )
        if not reviewer:
            raise PortfolioReviewError(
                f"{path} row {row_number}: reviewer is required"
            )
        _validate_reviewed_at(path, row_number, reviewed_at)
        reviews[client_site_id] = ManualReview(
            client_site_id=client_site_id,
            status=status,
            reviewer=reviewer,
            reviewed_at_utc=reviewed_at,
            notes=notes,
        )
    return reviews


def _validate_reviewed_at(path: Path, row_number: int, value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioReviewError(
            f"{path} row {row_number}: reviewed_at_utc must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        raise PortfolioReviewError(
            f"{path} row {row_number}: reviewed_at_utc must include a UTC offset"
        )
