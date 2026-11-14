#!/usr/bin/env python3
"""Validate and aggregate HDD price-per-terabyte snapshots.

Snapshots live in docs/hdd-prices/<YYYY-MM-DD>.csv and use a fixed schema.
One row per series and capacity per date: the cheapest qualifying in-stock
listing observed that day, recorded as a total price and as $/TB.

Method, definitions and historical results: docs/hdd-price-research.md.

Usage:
    scripts/hdd-price-index.py                    # validate every snapshot
    scripts/hdd-price-index.py --date 2026-11-09  # summarise one date
    scripts/hdd-price-index.py --date 2026-11-09 --format md
    scripts/hdd-price-index.py --fetch-diskprices # write today's new-sata snapshot
    scripts/hdd-price-index.py --compare 2026-09-01 --date 2026-11-09
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import urllib.error
import urllib.request
from datetime import date as _date
from html.parser import HTMLParser
from pathlib import Path

COLUMNS = [
    "date",
    "series",
    "capacity_tb",
    "condition",
    "recording",
    "price_usd",
    "price_per_tb",
    "drive",
    "url",
]
SERIES = {"new-cmr", "new-sata", "refurb-sata", "refurb-sas", "blended"}
CONDITIONS = {"new", "refurb", "used"}
RECORDINGS = {"cmr", "smr", "unknown"}
SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "docs" / "hdd-prices"
# Total price and $/TB are recorded independently by the sources; allow for
# rounding in the published per-terabyte figure.
PRICE_TOLERANCE = 0.01
# Series that pin the condition; blended and the rest accept any.
SERIES_CONDITION = {
    "new-cmr": "new",
    "new-sata": "new",
    "refurb-sata": "refurb",
    "refurb-sas": "refurb",
}
# Capacities collected per snapshot (docs/hdd-price-research.md, protocol step 2).
CAPACITIES = {4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32}
DISKPRICES_URL = "https://diskprices.com/?locale=us"
# diskprices.com answers 403 to urllib's default User-Agent.
USER_AGENT = "homelab-hdd-price-index/1.0"
_CAPACITY = re.compile(r"(\d+(?:\.\d+)?) TB")
_SAS = re.compile(r"\bSAS\b", re.IGNORECASE)
_ASIN = re.compile(r"/dp/([A-Z0-9]{10})")


class SnapshotError(Exception):
    """A snapshot violates the recording protocol."""


def _number(value: str, field: str, where: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SnapshotError(f"{where}: {field} is not a number: {value!r}") from None
    if number <= 0:
        raise SnapshotError(f"{where}: {field} must be positive: {value!r}")
    return number


def read_snapshot(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise SnapshotError(
                f"{path.name}: header must be exactly {','.join(COLUMNS)}"
            )
        rows = []
        for line, raw in enumerate(reader, start=2):
            where = f"{path.name}:{line}"
            if None in raw or None in raw.values():
                raise SnapshotError(f"{where}: expected {len(COLUMNS)} fields")
            try:
                _date.fromisoformat(raw["date"])
            except ValueError:
                raise SnapshotError(f"{where}: bad date {raw['date']!r}") from None
            if raw["series"] not in SERIES:
                raise SnapshotError(f"{where}: unknown series {raw['series']!r}")
            if raw["condition"] not in CONDITIONS:
                raise SnapshotError(f"{where}: unknown condition {raw['condition']!r}")
            if raw["recording"] not in RECORDINGS:
                raise SnapshotError(f"{where}: unknown recording {raw['recording']!r}")

            capacity = _number(raw["capacity_tb"], "capacity_tb", where)
            price = _number(raw["price_per_tb"], "price_per_tb", where)
            total_text = raw["price_usd"].strip()
            total = _number(total_text, "price_usd", where) if total_text else None
            if total is not None:
                implied = total / capacity
                if abs(implied - price) > max(PRICE_TOLERANCE, price * PRICE_TOLERANCE):
                    raise SnapshotError(
                        f"{where}: price_usd/capacity = {implied:.2f} but "
                        f"price_per_tb = {price:.2f}"
                    )
            expected = SERIES_CONDITION.get(raw["series"])
            if expected and raw["condition"] != expected:
                raise SnapshotError(f"{where}: {raw['series']} rows must be {expected}")
            if raw["series"] == "new-cmr" and raw["recording"] != "cmr":
                raise SnapshotError(f"{where}: new-cmr rows must be CMR")

            rows.append(
                {
                    "date": raw["date"],
                    "series": raw["series"],
                    "capacity_tb": capacity,
                    "condition": raw["condition"],
                    "recording": raw["recording"],
                    "price_usd": total,
                    "price_per_tb": price,
                    "drive": raw["drive"],
                    "url": raw["url"],
                    "where": where,
                }
            )

    if not rows:
        raise SnapshotError(f"{path.name}: no rows")
    for row in rows:
        if row["date"] != path.stem:
            raise SnapshotError(
                f"{row['where']}: date does not match filename {path.stem}"
            )

    seen = set()
    for row in rows:
        key = (row["date"], row["series"], row["capacity_tb"])
        if key in seen:
            raise SnapshotError(f"{row['where']}: duplicate {key}")
        seen.add(key)
    return rows


def summarize(rows: list[dict], series: str, minimum: int) -> dict:
    entries = sorted(
        (row for row in rows if row["series"] == series),
        key=lambda row: row["capacity_tb"],
    )
    if len(entries) < minimum:
        raise SnapshotError(
            f"series {series}: {len(entries)} capacities, expected at least {minimum}"
        )
    prices = [row["price_per_tb"] for row in entries]
    return {
        "entries": entries,
        "sweet": min(entries, key=lambda row: row["price_per_tb"]),
        "median": statistics.median(prices),
        "mean": statistics.fmean(prices),
    }


def _capacity(value: float) -> str:
    return f"{value:g}"


def render_text(snapshot: dict, series: str) -> str:
    lines = [f"series {series} · {len(snapshot['entries'])} capacities"]
    for row in snapshot["entries"]:
        marker = "  <- sweet spot" if row is snapshot["sweet"] else ""
        total = f"${row['price_usd']:.2f}" if row["price_usd"] else "n/a"
        lines.append(
            f"{_capacity(row['capacity_tb']):>5} TB  "
            f"${row['price_per_tb']:7.2f}/TB  {total:>10}{marker}"
        )
    lines.append(
        f"median ${snapshot['median']:.2f}/TB · mean ${snapshot['mean']:.2f}/TB"
    )
    return "\n".join(lines)


def render_markdown(snapshot: dict) -> str:
    lines = ["| Capacity | $/TB | Unit price |", "| --- | --- | --- |"]
    for row in snapshot["entries"]:
        total = f"${row['price_usd']:.2f}" if row["price_usd"] else "n/a"
        lines.append(
            f"| {_capacity(row['capacity_tb'])} TB | "
            f"${row['price_per_tb']:.2f} | {total} |"
        )
    return "\n".join(lines)


def render_comparison(before: dict, after: dict) -> str:
    old = {row["capacity_tb"]: row["price_per_tb"] for row in before["entries"]}
    new = {row["capacity_tb"]: row["price_per_tb"] for row in after["entries"]}
    shared = sorted(set(old) & set(new))
    if not shared:
        raise SnapshotError("comparison has no capacities in common")
    lines = ["| Capacity | Before | After | Change |", "| --- | --- | --- | --- |"]
    for capacity in shared:
        change = (new[capacity] - old[capacity]) / old[capacity] * 100
        lines.append(
            f"| {_capacity(capacity)} TB | ${old[capacity]:.2f} | "
            f"${new[capacity]:.2f} | {change:+.1f}% |"
        )
    median_change = (after["median"] - before["median"]) / before["median"] * 100
    lines.append("")
    lines.append(f"Median change: {median_change:+.1f}%")
    return "\n".join(lines)


class _DiskpricesParser(HTMLParser):
    """Collect <tr class="disk"> rows: product type, condition, cells, first link."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._row: dict | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and attrs.get("class") == "disk":
            self._row = {
                "type": attrs.get("data-product-type"),
                "condition": attrs.get("data-condition"),
                "cells": [],
                "href": None,
            }
        elif self._row is not None:
            if tag == "td":
                self._cell = []
            elif tag == "a" and self._row["href"] is None:
                self._row["href"] = attrs.get("href")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row["cells"].append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _money(text: str) -> float:
    return float(text.replace("$", "").replace(",", ""))


def parse_diskprices(page: str, day: str) -> list[dict]:
    """Cheapest new single-unit internal 3.5" SATA HDD per protocol capacity.

    diskprices.com does not publish recording technology, so rows are `unknown`
    and belong in the new-sata series, never new-cmr.
    """
    parser = _DiskpricesParser()
    parser.feed(page)
    parser.close()
    if not any(row["type"] == "internal_hdd" for row in parser.rows):
        raise SnapshotError("diskprices: no internal_hdd rows; page layout changed?")

    best: dict[float, dict] = {}
    for row in parser.rows:
        if row["type"] != "internal_hdd" or row["condition"] != "new":
            continue
        cells = row["cells"]
        if len(cells) != 9:
            raise SnapshotError(f"diskprices: expected 9 columns, got {len(cells)}")
        size = _CAPACITY.match(cells[3])  # multipacks ("4 TB x4") do not match
        if not size or float(size.group(1)) not in CAPACITIES:
            continue
        name = cells[8]
        if _SAS.search(name):  # SAS drives are listed under internal_hdd too
            continue
        asin = _ASIN.search(row["href"] or "")
        if not asin:
            raise SnapshotError(f"diskprices: no Amazon link for {name!r}")
        capacity = float(size.group(1))
        per_tb = _money(cells[1])
        if capacity not in best or per_tb < best[capacity]["per_tb"]:
            best[capacity] = {
                "per_tb": per_tb,
                "row": {
                    "date": day,
                    "series": "new-sata",
                    "capacity_tb": _capacity(capacity),
                    "condition": "new",
                    "recording": "unknown",
                    "price_usd": f"{_money(cells[2]):.2f}",
                    "price_per_tb": f"{per_tb:.2f}",
                    "drive": name,
                    # Canonical link; the page's affiliate tag stays out of the repo.
                    "url": f"https://www.amazon.com/dp/{asin.group(1)}",
                },
            }
    return [best[capacity]["row"] for capacity in sorted(best)]


def fetch_diskprices() -> str:
    request = urllib.request.Request(DISKPRICES_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as error:
        raise SnapshotError(f"diskprices fetch failed: {error}") from None


def collect_diskprices(directory: Path, minimum: int) -> Path:
    """Write today's diskprices.com snapshot; refuse to touch an existing one."""
    day = _date.today().isoformat()
    path = directory / f"{day}.csv"
    if path.exists():
        raise SnapshotError(f"{path.name} exists; snapshots are append-only")
    rows = parse_diskprices(fetch_diskprices(), day)
    if len(rows) < minimum:
        raise SnapshotError(
            f"diskprices: {len(rows)} capacities, expected at least {minimum}"
        )
    with path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    try:
        read_snapshot(path)
    except SnapshotError:
        path.unlink()
        raise
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and aggregate HDD price-per-TB snapshots."
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        help="snapshot CSV (default: every file in docs/hdd-prices)",
    )
    parser.add_argument("--date", help="summarise this snapshot date")
    parser.add_argument("--series", default="new-cmr", help="series to summarise")
    parser.add_argument("--compare", help="earlier date to compare against --date")
    parser.add_argument(
        "--format", choices=("text", "md"), default="text", help="output format"
    )
    parser.add_argument(
        "--min-capacities",
        type=int,
        default=8,
        help="refuse partial snapshots below this many capacities (default 8)",
    )
    parser.add_argument(
        "--fetch-diskprices",
        action="store_true",
        help="write today's new-sata snapshot from diskprices.com (never overwrites)",
    )
    args = parser.parse_args(argv)
    if args.compare and not args.date:
        parser.error("--compare requires --date")

    try:
        if args.fetch_diskprices:
            path = collect_diskprices(SNAPSHOT_DIR, args.min_capacities)
            print(f"wrote {path}")
            return 0
    except SnapshotError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    paths = args.input or sorted(SNAPSHOT_DIR.glob("*.csv"))
    if not paths:
        print(f"no snapshots in {SNAPSHOT_DIR}", file=sys.stderr)
        return 1

    try:
        rows = []
        for path in paths:
            rows.extend(read_snapshot(path))
        if args.date is None:
            dates = sorted({row["date"] for row in rows})
            print(
                f"validated {len(rows)} rows in {len(paths)} snapshot(s): {', '.join(dates)}"
            )
            return 0

        selected = [row for row in rows if row["date"] == args.date]
        if not selected:
            raise SnapshotError(f"no rows for {args.date}")
        snapshot = summarize(selected, args.series, args.min_capacities)
        previous = None
        if args.compare:
            earlier = [row for row in rows if row["date"] == args.compare]
            if not earlier:
                raise SnapshotError(f"no rows for {args.compare}")
            previous = summarize(earlier, args.series, args.min_capacities)
        output = (
            render_markdown(snapshot)
            if args.format == "md"
            else render_text(snapshot, args.series)
        )
        print(output)
        if previous is not None:
            print()
            print(render_comparison(previous, snapshot))
    except SnapshotError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
