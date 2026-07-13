"""Fetch a snapshot of all Vélo'v stations and append one row per station to
data/history.csv. Intended to run hourly via GitHub Actions so that, over time,
we can compute average availability for any given day-of-week and hour.
"""
import csv
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")

from source.utils import get_stations
from source.chart import render as render_chart

DATA_DIR = "data"
CSV_PATH = os.path.join(DATA_DIR, "history.csv")
README_PATH = "README.md"
README_START = "<!-- LATEST:START -->"
README_END = "<!-- LATEST:END -->"

FIELDNAMES = [
    "timestamp_utc",   # ISO-8601 UTC time the snapshot was collected
    "number",          # station id
    "name",
    "latitude",
    "longitude",
    "status",          # OPEN / CLOSED
    "bikes",           # total available bikes
    "electrical",
    "mechanical",
    "stands",          # free parking spots
    "capacity",
    "last_update",     # station's own lastUpdate timestamp
]


def build_rows(stations, timestamp):
    for station in stations:
        avail = station["totalStands"]["availabilities"]
        yield {
            "timestamp_utc": timestamp,
            "number": station["number"],
            "name": station["name"],
            "latitude": station["position"]["latitude"],
            "longitude": station["position"]["longitude"],
            "status": station["status"],
            "bikes": avail["bikes"],
            "electrical": avail["electricalBikes"],
            "mechanical": avail["mechanicalBikes"],
            "stands": avail["stands"],
            "capacity": station["totalStands"]["capacity"],
            "last_update": station.get("lastUpdate"),
        }


def update_readme(stations, collected_at):
    """Rewrite the LATEST section of the README with city-wide totals.

    ``collected_at`` is a timezone-aware datetime (not the CSV string).
    """
    electrical = sum(s["totalStands"]["availabilities"]["electricalBikes"] for s in stations)
    mechanical = sum(s["totalStands"]["availabilities"]["mechanicalBikes"] for s in stations)
    bikes = sum(s["totalStands"]["availabilities"]["bikes"] for s in stations)
    stands = sum(s["totalStands"]["availabilities"]["stands"] for s in stations)
    open_stations = sum(1 for s in stations if s.get("status") == "OPEN")

    block = (
        f"{README_START}\n"
        "<!-- This section is updated automatically every hour by the collect workflow. -->\n"
        "### 🚲 Latest update\n\n"
        # display the timestamp in French local time as HH:MM on DD/MM/YYYY
        f"**Latest update:** {collected_at.astimezone(PARIS_TZ).strftime('%H:%M on %d/%m/%Y')} (Local timezone)\n\n"
        f"- Electrical bikes available: **{electrical}**\n"
        f"- Mechanical bikes available: **{mechanical}**\n"
        f"- Total bikes available: **{bikes}**\n"
        f"- Free parking stands: **{stands}**\n"
        f"- Stations open: **{open_stations}/{len(stations)}**\n\n"
        f"**Dynamic data powered by Github Actions 🤖**\n"
        f"{README_END}"
    )

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find(README_START)
    end = content.find(README_END)
    if start == -1 or end == -1:
        print("README markers not found; skipping README update.")
        return
    new_content = content[:start] + block + content[end + len(README_END):]

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Updated README latest-update section.")


def main():
    stations = get_stations()
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    os.makedirs(DATA_DIR, exist_ok=True)
    file_exists = os.path.isfile(CSV_PATH)

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        count = 0
        for row in build_rows(stations, timestamp):
            writer.writerow(row)
            count += 1

    print(f"Wrote {count} station rows at {timestamp} to {CSV_PATH}")

    update_readme(stations, collected_at)
    render_chart()


if __name__ == "__main__":
    main()
