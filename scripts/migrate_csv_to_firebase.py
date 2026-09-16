#!/usr/bin/env python3
"""Migrate historical data from data/history.csv into Cloud Firestore.

Usage:
  python3 scripts/migrate_csv_to_firebase.py [options]

Options:
  --csv-path PATH       Path to history.csv (default: data/history.csv)
  --batch-size N        Firestore batch size (default: 450, max: 500)
  --since DATE          Only migrate records since this UTC date (e.g. 2026-09-01)
  --limit N             Only process the first N CSV rows (for dry testing)
  --latest-only         Only upload the most recent snapshot as system/latest_state
  --dry-run             Parse and validate CSV without writing to Firestore
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from source.firebase_db import (
    get_firestore_client,
    is_firebase_configured,
    arrondissement_of,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate Vélo'v CSV data to Cloud Firestore")
    parser.add_argument("--csv-path", default="data/history.csv", help="Path to history.csv")
    parser.add_argument("--batch-size", type=int, default=450, help="Batch size (max 500)")
    parser.add_argument("--since", default=None, help="Filter records >= ISO date (e.g. 2026-09-01)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows processed")
    parser.add_argument("--latest-only", action="store_true", help="Only upload latest snapshot to system/latest_state")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to Firestore")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.csv_path):
        print(f"Error: File not found: {args.csv_path}")
        sys.exit(1)

    if not args.dry_run:
        if not is_firebase_configured():
            print("Error: Firebase is not configured.")
            print("Please set FIREBASE_SERVICE_ACCOUNT (JSON string) or FIREBASE_CREDENTIALS_PATH in your environment or .env file.")
            sys.exit(1)
        db = get_firestore_client()
    else:
        print("[Dry Run Mode] Firebase writes will be skipped.")
        db = None

    print(f"Reading {args.csv_path}...")
    start_time = time.time()

    # Track data
    # snapshots[ts] -> list of station dicts
    snapshots = defaultdict(list)
    latest_by_station = {}
    total_rows = 0

    with open(args.csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            if args.limit and total_rows > args.limit:
                break

            ts = row["timestamp_utc"]
            if args.since and ts < args.since:
                continue

            station_number = row["number"]
            station_info = {
                "number": station_number,
                "name": row["name"],
                "latitude": float(row["latitude"]) if row["latitude"] else 0.0,
                "longitude": float(row["longitude"]) if row["longitude"] else 0.0,
                "status": row["status"],
                "bikes": int(row["bikes"]) if row["bikes"] else 0,
                "electrical": int(row["electrical"]) if row["electrical"] else 0,
                "mechanical": int(row["mechanical"]) if row["mechanical"] else 0,
                "stands": int(row["stands"]) if row["stands"] else 0,
                "capacity": int(row["capacity"]) if row["capacity"] else 0,
                "last_update": row.get("last_update", ""),
                "timestamp_utc": ts,
            }

            snapshots[ts].append(station_info)
            latest_by_station[station_number] = station_info

    sorted_timestamps = sorted(snapshots.keys())
    print(f"Loaded {total_rows} rows across {len(sorted_timestamps)} snapshots and {len(latest_by_station)} unique stations.")
    if not sorted_timestamps:
        print("No snapshots found matching filters.")
        return

    latest_ts = sorted_timestamps[-1]
    latest_snapshot_stations = snapshots[latest_ts]

    # Compute latest_state
    total_elec = sum(s["electrical"] for s in latest_snapshot_stations)
    total_mech = sum(s["mechanical"] for s in latest_snapshot_stations)
    total_bikes = sum(s["bikes"] for s in latest_snapshot_stations)
    total_stands = sum(s["stands"] for s in latest_snapshot_stations)
    open_count = sum(1 for s in latest_snapshot_stations if s["status"] == "OPEN")

    arr_elec = {arr: 0 for arr in range(1, 10)}
    for s in latest_snapshot_stations:
        arr = arrondissement_of(s["number"])
        if arr in arr_elec:
            arr_elec[arr] += s["electrical"]

    latest_state_payload = {
        "timestamp_utc": latest_ts,
        "stations_count": len(latest_snapshot_stations),
        "total_bikes": total_bikes,
        "electrical": total_elec,
        "mechanical": total_mech,
        "stands": total_stands,
        "open_stations": open_count,
        "by_arrondissement": {str(k): v for k, v in arr_elec.items()},
        "stations": latest_snapshot_stations,
    }

    if args.dry_run:
        print("\n--- Dry Run Summary ---")
        print(f"Latest snapshot timestamp: {latest_ts}")
        print(f"Total bikes: {total_bikes} (elec: {total_elec}, mech: {total_mech})")
        print(f"Free stands: {total_stands}, Open stations: {open_count}/{len(latest_snapshot_stations)}")
        print(f"Would write system/latest_state with {len(latest_snapshot_stations)} stations.")
        if not args.latest_only:
            total_ops = len(sorted_timestamps) + len(latest_by_station) + total_rows
            print(f"Would write ~{len(sorted_timestamps)} city_snapshots docs.")
            print(f"Would write {len(latest_by_station)} station docs.")
            print(f"Would write ~{total_rows} station history docs in batches of {args.batch_size}.")
            print(f"Estimated total Firestore operations: {total_ops}")
        return

    # Write system/latest_state first
    print(f"\n[1/3] Uploading system/latest_state ({latest_ts})...")
    db.collection("system").document("latest_state").set(latest_state_payload)
    print("Done!")

    if args.latest_only:
        print("Completed (--latest-only).")
        return

    # Write city_snapshots
    print(f"\n[2/3] Uploading {len(sorted_timestamps)} city_snapshots...")
    batch = db.batch()
    batch_ops = 0
    total_city_written = 0

    for ts in sorted_timestamps:
        st_list = snapshots[ts]
        t_elec = sum(s["electrical"] for s in st_list)
        t_mech = sum(s["mechanical"] for s in st_list)
        t_bikes = sum(s["bikes"] for s in st_list)
        t_stands = sum(s["stands"] for s in st_list)
        o_count = sum(1 for s in st_list if s["status"] == "OPEN")

        a_elec = {arr: 0 for arr in range(1, 10)}
        for s in st_list:
            arr = arrondissement_of(s["number"])
            if arr in a_elec:
                a_elec[arr] += s["electrical"]

        city_doc = {
            "timestamp_utc": ts,
            "total_bikes": t_bikes,
            "electrical": t_elec,
            "mechanical": t_mech,
            "stands": t_stands,
            "open_stations": o_count,
            "stations_count": len(st_list),
            "by_arrondissement": {str(k): v for k, v in a_elec.items()},
        }
        safe_id = ts.replace(":", "-")
        ref = db.collection("city_snapshots").document(safe_id)
        batch.set(ref, city_doc)
        batch_ops += 1

        if batch_ops >= args.batch_size:
            batch.commit()
            total_city_written += batch_ops
            batch = db.batch()
            batch_ops = 0

    if batch_ops > 0:
        batch.commit()
        total_city_written += batch_ops
    print(f"Wrote {total_city_written} city_snapshots documents.")

    # Write station documents and history
    print(f"\n[3/3] Uploading {len(latest_by_station)} station docs and {total_rows} history entries...")
    batch = db.batch()
    batch_ops = 0
    committed_ops = 0
    start_history_time = time.time()

    # Seed latest station docs
    for number, st in latest_by_station.items():
        ref = db.collection("stations").document(str(number))
        batch.set(ref, st, merge=True)
        batch_ops += 1
        if batch_ops >= args.batch_size:
            batch.commit()
            committed_ops += batch_ops
            batch = db.batch()
            batch_ops = 0

    # Write history
    for ts in sorted_timestamps:
        safe_id = ts.replace(":", "-")
        for st in snapshots[ts]:
            ref = db.collection("stations").document(str(st["number"])).collection("history").document(safe_id)
            batch.set(ref, {
                "timestamp_utc": ts,
                "bikes": st["bikes"],
                "electrical": st["electrical"],
                "mechanical": st["mechanical"],
                "stands": st["stands"],
                "capacity": st["capacity"],
                "status": st["status"],
            })
            batch_ops += 1

            if batch_ops >= args.batch_size:
                batch.commit()
                committed_ops += batch_ops
                batch = db.batch()
                batch_ops = 0

                elapsed = time.time() - start_history_time
                rate = committed_ops / elapsed if elapsed > 0 else 0
                pct = (committed_ops / (total_rows + len(latest_by_station))) * 100
                print(f"Progress: {committed_ops} ops ({pct:.1f}%) - {rate:.0f} ops/sec", end="\r")

    if batch_ops > 0:
        batch.commit()
        committed_ops += batch_ops

    total_time = time.time() - start_time
    print(f"\nMigration complete! Total operations: {committed_ops} in {total_time:.1f}s.")


if __name__ == "__main__":
    main()
