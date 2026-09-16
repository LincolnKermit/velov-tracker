"""Fetch a snapshot of all Vélo'v stations and append one row per station to
data/history.csv. Intended to run every 15 minutes locally on a Raspberry Pi so that,
over time, we can compute average availability for any given day-of-week and hour.
"""
import csv
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")

from source.utils import get_stations
from source.chart import render as render_chart
from source.chart import render_by_arrondissement as render_arr_chart
from source.firebase_db import save_snapshot, is_firebase_configured

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
        "<!-- This section is updated automatically every 15 minutes by the collect workflow. -->\n"
        "### 🚲 Latest update\n\n"
        # display the timestamp in French local time as HH:MM on DD/MM/YYYY
        f"**Latest update:** {collected_at.astimezone(PARIS_TZ).strftime('%H:%M on %d/%m/%Y')} (Local timezone)\n\n"
        f"- Electrical bikes available: **{electrical}**\n"
        f"- Mechanical bikes available: **{mechanical}**\n"
        f"- Total bikes available: **{bikes}**\n"
        f"- Free parking stands: **{stands}**\n"
        f"- Stations open: **{open_stations}/{len(stations)}**\n\n"
        f"**Dynamic data powered by Raspberry Pi 🍓**\n"
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


RECENT_JSON_PATH = os.path.join(DATA_DIR, "recent_history.json")


def update_recent_history_json(stations, timestamp):
    """Keep rolling 24-hour window in data/recent_history.json."""
    data = {}
    if os.path.isfile(RECENT_JSON_PATH):
        try:
            import json
            with open(RECENT_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    for s in stations:
        num = str(s.get("number"))
        avail = s.get("totalStands", {}).get("availabilities", {})
        point = [
            timestamp,
            int(avail.get("electricalBikes", 0)),
            int(avail.get("mechanicalBikes", 0)),
            int(avail.get("bikes", 0)),
            int(avail.get("stands", 0)),
            int(s.get("totalStands", {}).get("capacity", 0)),
        ]
        if num not in data:
            data[num] = []
        data[num].append(point)
        data[num] = [p for p in data[num] if (p[0] if isinstance(p, list) else p.get("timestamp_utc", "")) >= cutoff]

    try:
        import json
        with open(RECENT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception as e:
        print(f"[Warning] Failed to update {RECENT_JSON_PATH}: {e}")


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

    # Update local rolling 24-hour cache
    update_recent_history_json(stations, timestamp)

    # Push to Firebase if configured
    if is_firebase_configured():
        try:
            print("Uploading snapshot to Firebase Firestore...")
            save_snapshot(stations, timestamp)
        except Exception as e:
            print(f"[Warning] Firebase snapshot upload failed: {e}")
    else:
        print("[Info] Firebase not configured; skipping cloud sync.")

    update_readme(stations, collected_at)
    render_chart()
    render_arr_chart()



if __name__ == "__main__":
    main()
