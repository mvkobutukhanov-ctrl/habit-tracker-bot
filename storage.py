"""SQLite layer for the habit tracker bot."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from contextlib import contextmanager

WATER_TARGET = 12
PROTEIN_TARGET = 150

BINARY_FIELDS = (
    "morning_shower",
    "morning_walk",
    "evening_walk",
    "no_porn",
    "no_masturbation",
    "no_shorts",
    "sleep",
)


@dataclass
class DayState:
    date: str
    morning_shower: bool = False
    morning_walk: bool = False
    water_count: int = 0
    protein_g: int = 0
    evening_walk: bool = False
    no_porn: bool = False
    no_masturbation: bool = False
    no_shorts: bool = False
    sleep: bool = False

    def is_closed(self) -> bool:
        return (
            self.morning_shower
            and self.morning_walk
            and self.water_count >= WATER_TARGET
            and self.protein_g >= PROTEIN_TARGET
            and self.evening_walk
            and self.no_porn
            and self.no_masturbation
            and self.no_shorts
            and self.sleep
        )

    def checked_count(self) -> int:
        return sum(
            (
                self.morning_shower,
                self.morning_walk,
                self.water_count >= WATER_TARGET,
                self.protein_g >= PROTEIN_TARGET,
                self.evening_walk,
                self.no_porn,
                self.no_masturbation,
                self.no_shorts,
                self.sleep,
            )
        )


@dataclass
class HistoryRow:
    date: str
    checked_count: int
    is_closed: bool


_DB_PATH: str | None = None


def init_db(path: str) -> None:
    """Set the DB path and create the schema if missing."""
    global _DB_PATH
    _DB_PATH = path
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_log (
                date TEXT PRIMARY KEY,
                morning_shower INTEGER NOT NULL DEFAULT 0,
                morning_walk INTEGER NOT NULL DEFAULT 0,
                water_count INTEGER NOT NULL DEFAULT 0,
                protein_g INTEGER NOT NULL DEFAULT 0,
                evening_walk INTEGER NOT NULL DEFAULT 0,
                no_porn INTEGER NOT NULL DEFAULT 0,
                no_masturbation INTEGER NOT NULL DEFAULT 0,
                no_shorts INTEGER NOT NULL DEFAULT 0,
                sleep INTEGER NOT NULL DEFAULT 0
            )
            """
        )


@contextmanager
def _connect():
    if _DB_PATH is None:
        raise RuntimeError("init_db() must be called before any DB operation")
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_day(date_iso: str) -> DayState:
    """Return DayState for the given date; defaults if no row."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM daily_log WHERE date = ?", (date_iso,)
        ).fetchone()
    if row is None:
        return DayState(date=date_iso)
    return DayState(
        date=row["date"],
        morning_shower=bool(row["morning_shower"]),
        morning_walk=bool(row["morning_walk"]),
        water_count=int(row["water_count"]),
        protein_g=int(row["protein_g"]),
        evening_walk=bool(row["evening_walk"]),
        no_porn=bool(row["no_porn"]),
        no_masturbation=bool(row["no_masturbation"]),
        no_shorts=bool(row["no_shorts"]),
        sleep=bool(row["sleep"]),
    )


def _ensure_row(conn: sqlite3.Connection, date_iso: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO daily_log (date) VALUES (?)", (date_iso,)
    )


def set_binary(date_iso: str, key: str, value: bool) -> None:
    """Set one of the binary fields to value (0/1). Key must be in BINARY_FIELDS."""
    if key not in BINARY_FIELDS:
        raise ValueError(f"unknown binary field: {key}")
    with _connect() as conn:
        _ensure_row(conn, date_iso)
        conn.execute(
            f"UPDATE daily_log SET {key} = ? WHERE date = ?",
            (1 if value else 0, date_iso),
        )


def bump_water(date_iso: str, delta: int) -> None:
    """Adjust water count by delta, clamped to [0, WATER_TARGET]."""
    with _connect() as conn:
        _ensure_row(conn, date_iso)
        row = conn.execute(
            "SELECT water_count FROM daily_log WHERE date = ?", (date_iso,)
        ).fetchone()
        new_val = max(0, min(WATER_TARGET, int(row["water_count"]) + delta))
        conn.execute(
            "UPDATE daily_log SET water_count = ? WHERE date = ?",
            (new_val, date_iso),
        )


def bump_protein(date_iso: str, delta: int) -> None:
    """Adjust protein grams by delta, clamped to [0, ∞)."""
    with _connect() as conn:
        _ensure_row(conn, date_iso)
        row = conn.execute(
            "SELECT protein_g FROM daily_log WHERE date = ?", (date_iso,)
        ).fetchone()
        new_val = max(0, int(row["protein_g"]) + delta)
        conn.execute(
            "UPDATE daily_log SET protein_g = ? WHERE date = ?",
            (new_val, date_iso),
        )


def reset_protein(date_iso: str) -> None:
    with _connect() as conn:
        _ensure_row(conn, date_iso)
        conn.execute(
            "UPDATE daily_log SET protein_g = 0 WHERE date = ?", (date_iso,)
        )


def get_history(n_days: int, today_iso: str) -> list[HistoryRow]:
    """Return last n_days of history (most recent first), starting from today_iso."""
    from datetime import date as _date, timedelta

    base = _date.fromisoformat(today_iso)
    dates = [(base - timedelta(days=i)).isoformat() for i in range(n_days)]
    rows: list[HistoryRow] = []
    for d in dates:
        state = get_day(d)
        rows.append(
            HistoryRow(
                date=d,
                checked_count=state.checked_count(),
                is_closed=state.is_closed(),
            )
        )
    return rows


def compute_streaks(today_iso: str) -> tuple[int, int]:
    """Return (current_streak, best_streak).

    current_streak: consecutive closed days ending at today or yesterday (whichever
    is the most recent closed day). 0 if neither today nor yesterday is closed.
    best_streak: max consecutive closed days anywhere in history.
    """
    from datetime import date as _date, timedelta

    with _connect() as conn:
        all_rows = conn.execute("SELECT * FROM daily_log").fetchall()
    if not all_rows:
        return 0, 0

    closed_dates: set[str] = set()
    for r in all_rows:
        state = DayState(
            date=r["date"],
            morning_shower=bool(r["morning_shower"]),
            morning_walk=bool(r["morning_walk"]),
            water_count=int(r["water_count"]),
            protein_g=int(r["protein_g"]),
            evening_walk=bool(r["evening_walk"]),
            no_porn=bool(r["no_porn"]),
            no_masturbation=bool(r["no_masturbation"]),
            no_shorts=bool(r["no_shorts"]),
            sleep=bool(r["sleep"]),
        )
        if state.is_closed():
            closed_dates.add(state.date)

    if not closed_dates:
        return 0, 0

    # Best streak: longest contiguous run of closed dates anywhere.
    sorted_closed = sorted(_date.fromisoformat(d) for d in closed_dates)
    best = 1
    run = 1
    for i in range(1, len(sorted_closed)):
        if sorted_closed[i] - sorted_closed[i - 1] == timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1

    # Current streak: anchor on today if closed, else yesterday if closed, else 0.
    today_d = _date.fromisoformat(today_iso)
    anchor: _date | None = None
    if today_iso in closed_dates:
        anchor = today_d
    elif (today_d - timedelta(days=1)).isoformat() in closed_dates:
        anchor = today_d - timedelta(days=1)
    if anchor is None:
        return 0, best

    current = 0
    cursor = anchor
    while cursor.isoformat() in closed_dates:
        current += 1
        cursor -= timedelta(days=1)

    return current, best
