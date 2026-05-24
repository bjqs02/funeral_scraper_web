"""Fetch farewell + coffin data, merge, and write docs/data/latest.json.

This is the entrypoint invoked by .github/workflows/scrape.yml on a cron
schedule. The output JSON is consumed by docs/app.js running in the browser
(GitHub Pages). No xlsx, no Streamlit, no dedup state — the static docs
just shows whatever the latest scrape produced.

Usage:
    python scripts/scrape_to_json.py            # 7 days, default output path
    python scripts/scrape_to_json.py --days 14
    python scripts/scrape_to_json.py --out custom/path.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scraper_core import (  # noqa: E402
    COFFIN_URL,
    FAREWELL_URL,
    SLEEP_BETWEEN_REQUESTS_SEC,
    UNIT_CODE_CHONGDE,
    UNIT_NAME_CHONGDE,
    CoffinDayRoom,
    FarewellRecord,
    _COFFIN_HALL_RE,
    _roc_date,
    fetch_coffin_day,
    fetch_farewell_day,
    merge_coffin_into_farewell,
    parse_coffin,
    parse_farewell,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "data" / "latest.json"


def build_visit_schedule(records: list[FarewellRecord]) -> list[dict]:
    # Cross-product (date × person) over each person's visiting window —
    # mirrors the 致意排程 sheet logic in scraper.py's _write_visit_schedule_sheet.
    rows: list[dict] = []
    for rec in records:
        if rec.visit_start_date:
            try:
                start = datetime.strptime(rec.visit_start_date, "%Y/%m/%d").date()
                end = datetime.strptime(
                    rec.visit_end_date or rec.visit_start_date, "%Y/%m/%d").date()
            except ValueError:
                continue
            cursor = start
            while cursor <= end:
                rows.append({
                    "visit_date": cursor.strftime("%Y/%m/%d"),
                    "name": rec.name, "gender": rec.gender, "age": rec.age,
                    "residence": rec.residence,
                    "visit_location": rec.visit_location,
                    "farewell_date": rec.farewell_date,
                    "time_range": rec.time_range,
                    "public_ceremony": rec.public_ceremony,
                    "hall": rec.hall,
                    "visit_note": rec.visit_note,
                })
                cursor += timedelta(days=1)
        elif _COFFIN_HALL_RE.match(rec.hall):
            rows.append({
                "visit_date": rec.farewell_date,
                "name": rec.name, "gender": rec.gender, "age": rec.age,
                "residence": rec.residence,
                "visit_location": rec.visit_location,
                "farewell_date": rec.farewell_date,
                "time_range": rec.time_range,
                "public_ceremony": rec.public_ceremony,
                "hall": rec.hall,
                "visit_note": rec.visit_note,
            })
    rows.sort(key=lambda r: (r["visit_date"], r["name"]))
    return rows


def scrape(days: int) -> dict:
    today = date.today()
    end_day = today + timedelta(days=days - 1)
    scraped_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

    print(f"[info] 抓取 {UNIT_NAME_CHONGDE} 場次: {today} ~ {end_day} ({days} 天)")

    all_records: list[FarewellRecord] = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        try:
            page = fetch_farewell_day(UNIT_CODE_CHONGDE, day)
        except Exception as exc:
            print(f"[error] 告別式 {day} 抓取失敗: {exc!r}", file=sys.stderr)
            continue
        recs = parse_farewell(
            page,
            unit_name=UNIT_NAME_CHONGDE,
            source_url=FAREWELL_URL,
            scraped_at=scraped_at,
        )
        print(f"[info] 告別式 {day} ({_roc_date(day)}): {len(recs)} 筆")
        all_records.extend(recs)
        time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

    # See FarewellRecord.dedup_key — collapses repeats across query days.
    dedup: dict[str, FarewellRecord] = {}
    for rec in all_records:
        dedup.setdefault(rec.dedup_key(), rec)
    deduped = list(dedup.values())

    coffin_records: list[CoffinDayRoom] = []
    try:
        page = fetch_coffin_day(UNIT_CODE_CHONGDE, today)
        coffin_records = parse_coffin(
            page, unit_name=UNIT_NAME_CHONGDE, query_year=today.year)
        print(f"[info] 停柩室矩陣: {len(coffin_records)} 筆 (涵蓋未來 ~20 天)")
    except Exception as exc:
        print(f"[error] 停柩室抓取失敗: {exc!r}", file=sys.stderr)

    merge_coffin_into_farewell(deduped, coffin_records)

    matched = sum(1 for f in deduped if f.visit_start_date)
    in_coffin_room = sum(
        1 for f in deduped if not f.visit_start_date and _COFFIN_HALL_RE.match(f.hall))
    formal_hall = sum(
        1 for f in deduped if not f.visit_start_date
        and not _COFFIN_HALL_RE.match(f.hall))
    print(
        f"[info] 對映結果: 有公開致意期間 {matched} / "
        f"告別式於停柩室現場 {in_coffin_room} / "
        f"正式禮廳(致意資訊未公開) {formal_hall}"
    )

    deduped.sort(key=lambda r: (r.farewell_date, r.time_range, r.hall))
    coffin_records.sort(key=lambda r: (r.occupancy_date, r.room_number))

    return {
        "meta": {
            "generated_at_utc": scraped_at,
            "date_range": {
                "start": today.strftime("%Y/%m/%d"),
                "end": end_day.strftime("%Y/%m/%d"),
                "days": days,
            },
            "unit": UNIT_NAME_CHONGDE,
            "source": {
                "farewell_url": FAREWELL_URL,
                "coffin_url": COFFIN_URL,
            },
            "stats": {
                "total_farewells": len(deduped),
                "with_visit_window": matched,
                "on_coffin_room": in_coffin_room,
                "formal_hall": formal_hall,
                "coffin_rows": len(coffin_records),
            },
        },
        "farewells": [asdict(r) for r in deduped],
        "coffin_rooms": [asdict(r) for r in coffin_records],
        "visit_schedule": build_visit_schedule(deduped),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7, help="未來 N 天 (預設 7)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"輸出 JSON 路徑 (預設 {DEFAULT_OUT.relative_to(ROOT)})")
    args = ap.parse_args(argv)
    if args.days <= 0 or args.days > 60:
        ap.error("--days 應為 1~60")

    payload = scrape(days=args.days)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] 輸出: {args.out} "
          f"({len(payload['farewells'])} farewells, "
          f"{len(payload['visit_schedule'])} visit rows, "
          f"{len(payload['coffin_rooms'])} coffin rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())