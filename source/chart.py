"""Render charts of Vélo'v availability over the last 24 hours from
data/history.csv into assets/availability.svg and
assets/availability_by_arrondissement.svg.

Chronological snapshots over the rolling 24-hour window are plotted with the
oldest point on the left and the latest updated info on the rightmost edge.

Run standalone (``python -m source.chart``) or via ``source.collect`` after a
snapshot is appended. The image is regenerated in place every run, so the README
reference to it never needs to change.
"""
import csv
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless: no display in CI
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

PARIS_TZ = ZoneInfo("Europe/Paris")

try:
    from source.firebase_db import (
        is_firebase_configured,
        get_station_history,
        get_station_info,
        get_city_snapshots,
    )
except ImportError:
    is_firebase_configured = lambda: False
    get_station_history = None
    get_station_info = None
    get_city_snapshots = None


# Rolling window used by the per-station chart.
WINDOW_HOURS = 24

CSV_PATH = os.path.join("data", "history.csv")
ASSETS_DIR = "assets"
CHART_PATH = os.path.join(ASSETS_DIR, "availability.svg")
ARR_CHART_PATH = os.path.join(ASSETS_DIR, "availability_by_arrondissement.svg")
# Per-station charts are generated on demand (one file per request) so they
# each get a unique name and never clobber one another.
STATION_HISTORY_DIR = os.path.join("static", "history")

# Palette (validated dark surface — reads on both GitHub light and dark themes
# because the image carries its own background).
SURFACE = "#262626"
INK = "#C2C2C2"
MUTED = "#898781"
GRID = "#e1e0d9"
TOTAL = "#3d3d3d"      # blue    — total bikes
ELECTRICAL = "#007f1c"  # green   — electrical bikes (rgb 0,127,28)
MECHANICAL = "#eb6834"  # orange  — mechanical bikes
LOW = "#d03b3b"        # status critical — marks the lowest total point
MAX_CAPACITY_LINE = "#eb4934"

# Distinct hue per Lyon arrondissement (1er → 9e). Chosen to stay legible
# against the dark SURFACE and to keep neighbouring lines separable.
ARR_COLORS = {
    1: "#2a78d6",  # blue
    2: "#eb6834",  # orange
    3: "#007f1c",  # green
    4: "#d03b3b",  # red
    5: "#9b5de5",  # purple
    6: "#00b4b4",  # teal
    7: "#e0b400",  # gold
    8: "#e05299",  # pink
    9: "#8a6d3b",  # brown
}


def load_hourly_profile():
    """Aggregate the CSV into average city-wide availability per hour of day.

    Returns (hours, total, electrical, mechanical): parallel lists over the
    local hours (0-23) that have at least one snapshot, sorted ascending.
    """
    # For each snapshot timestamp, the city-wide totals available.
    snap_total = defaultdict(int)
    snap_elec = defaultdict(int)
    snap_mech = defaultdict(int)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp_utc"]
            snap_total[ts] += int(row["bikes"])
            snap_elec[ts] += int(row["electrical"])
            snap_mech[ts] += int(row["mechanical"])

    # Bucket each snapshot by its local hour of day, then average per hour.
    sums = defaultdict(lambda: [0.0, 0.0, 0.0])
    counts = defaultdict(int)
    for ts in snap_total:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        hour = dt.astimezone(PARIS_TZ).hour
        sums[hour][0] += snap_total[ts]
        sums[hour][1] += snap_elec[ts]
        sums[hour][2] += snap_mech[ts]
        counts[hour] += 1

    hours = sorted(sums)
    total = [sums[h][0] / counts[h] for h in hours]
    electrical = [sums[h][1] / counts[h] for h in hours]
    mechanical = [sums[h][2] / counts[h] for h in hours]
    return hours, total, electrical, mechanical


def load_recent_citywide():
    """Read the CSV into chronological city-wide totals over the last WINDOW_HOURS.

    Returns (times, total, electrical, mechanical) where ``times`` is a sorted list
    of Europe/Paris datetimes within the last 24 hours, ending with the most recent
    snapshot as the rightmost element.
    """
    snap_total = defaultdict(int)
    snap_elec = defaultdict(int)
    snap_mech = defaultdict(int)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp_utc"]
            snap_total[ts] += int(row["bikes"])
            snap_elec[ts] += int(row["electrical"])
            snap_mech[ts] += int(row["mechanical"])

    if not snap_total:
        return [], [], [], []

    sorted_ts = sorted(snap_total)
    latest_dt = datetime.strptime(sorted_ts[-1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    cutoff = latest_dt.timestamp() - WINDOW_HOURS * 3600

    times = []
    total = []
    electrical = []
    mechanical = []
    for ts in sorted_ts:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if dt.timestamp() < cutoff:
            continue
        times.append(dt.astimezone(PARIS_TZ))
        total.append(snap_total[ts])
        electrical.append(snap_elec[ts])
        mechanical.append(snap_mech[ts])

    return times, total, electrical, mechanical


def arrondissement_of(number):
    """Map a Vélo'v station number to its Lyon arrondissement (1-9), or None.

    Station numbers are prefixed by district: a single leading digit 1-9 within
    a 4-digit number is one of Lyon's nine arrondissements (e.g. 2010 -> 2e,
    5015 -> 5e). Numbers >= 10000 are Villeurbanne / surrounding communes and
    are excluded.
    """
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    if 1000 <= n <= 9999:
        return n // 1000
    return None


def load_recent_by_arrondissement():
    """Read the CSV into chronological per-snapshot electrical-bike totals for
    each Lyon arrondissement over the last WINDOW_HOURS.

    Returns (times, series) where ``times`` is a sorted list of Europe/Paris
    datetimes and ``series`` maps arrondissement number -> list of electrical
    bike counts parallel to ``times``.
    """
    # {timestamp: {arrondissement: electrical bikes}}
    snap = defaultdict(lambda: defaultdict(int))
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            arr = arrondissement_of(row["number"])
            if arr is None:
                continue
            snap[row["timestamp_utc"]][arr] += int(row["electrical"])

    if not snap:
        return [], {}

    sorted_ts = sorted(snap)
    latest_dt = datetime.strptime(sorted_ts[-1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    cutoff = latest_dt.timestamp() - WINDOW_HOURS * 3600

    times = []
    series = {arr: [] for arr in sorted(ARR_COLORS)}
    for ts in sorted_ts:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if dt.timestamp() < cutoff:
            continue
        times.append(dt.astimezone(PARIS_TZ))
        for arr in series:
            series[arr].append(snap[ts].get(arr, 0))

    return times, series


def render_by_arrondissement():
    times, series = load_recent_by_arrondissement()
    if not times:
        print("No data to plot; skipping arrondissement chart.")
        return

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    for arr in sorted(series):
        ax.plot(times, series[arr], color=ARR_COLORS[arr], linewidth=2,
                marker="o", markersize=3, label=f"{arr}e")

    ax.set_title("Electrical bikes available by arrondissement — last 24 hours",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome (matches the city-wide chart).
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.margins(x=0.02)
    ax.set_ylim(bottom=0)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=PARIS_TZ))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh\n%d/%m", tz=PARIS_TZ))

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=9,
                       columnspacing=0.9)
    legend.set_zorder(6)

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.18)

    os.makedirs(ASSETS_DIR, exist_ok=True)
    fig.savefig(ARR_CHART_PATH, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote last-24h arrondissement chart with {len(times)} points to {ARR_CHART_PATH}")


def load_station_recent(station_id):
    """Read chronological electrical/mechanical availability for a
    single station over the last WINDOW_HOURS from Firestore (or CSV fallback).

    Returns (name, times, electrical, mechanical, capacity).
    """
    station_id = str(station_id)

    # 1. Try Firebase first if configured
    if is_firebase_configured() and get_station_history:
        info = get_station_info(station_id) if get_station_info else {}
        name = info.get("name") if info else None
        capacity = int(info.get("capacity", 0)) if info else 0

        hist = get_station_history(station_id, hours=WINDOW_HOURS)
        if hist:
            times = []
            electrical = []
            mechanical = []
            max_capacity = capacity
            for r in hist:
                dt = datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                times.append(dt.astimezone(PARIS_TZ))
                electrical.append(r["electrical"])
                mechanical.append(r["mechanical"])
                max_capacity = max(max_capacity, r.get("capacity", 0))
            return name, times, electrical, mechanical, max_capacity

    # 2. Fallback to local CSV
    name = None
    rows = []  # (utc datetime, electrical, mechanical, capacity)
    if os.path.isfile(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["number"] != station_id:
                    continue
                name = row["name"]
                dt = datetime.strptime(row["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                rows.append((dt, int(row["electrical"]), int(row["mechanical"]), int(row["capacity"])))

    if not rows:
        return name, [], [], [], 0

    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_HOURS * 3600
    rows.sort(key=lambda r: r[0])

    times, electrical, mechanical = [], [], []
    max_capacity = 0
    for dt, elec, mech, cap in rows:
        if dt.timestamp() < cutoff:
            continue
        times.append(dt.astimezone(PARIS_TZ))
        electrical.append(elec)
        mechanical.append(mech)
        max_capacity = max(max_capacity, cap)

    return name, times, electrical, mechanical, max_capacity


def load_station_all(station_id):
    """Read chronological electrical/mechanical availability for a
    single station over its entire recorded history from Firestore (or CSV fallback).

    Returns (name, times, electrical, mechanical).
    """
    station_id = str(station_id)

    # 1. Try Firebase first if configured
    if is_firebase_configured() and get_station_history:
        info = get_station_info(station_id) if get_station_info else {}
        name = info.get("name") if info else None

        hist = get_station_history(station_id, hours=None, all_history=True)
        if hist:
            times = []
            electrical = []
            mechanical = []
            for r in hist:
                dt = datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                times.append(dt.astimezone(PARIS_TZ))
                electrical.append(r["electrical"])
                mechanical.append(r["mechanical"])
            return name, times, electrical, mechanical

    # 2. Fallback to local CSV
    name = None
    rows = []  # (utc datetime, electrical, mechanical)
    if os.path.isfile(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["number"] != station_id:
                    continue
                name = row["name"]
                dt = datetime.strptime(row["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                rows.append((dt, int(row["electrical"]), int(row["mechanical"])))

    if not rows:
        return name, [], [], []

    rows.sort(key=lambda r: r[0])

    times = [dt.astimezone(PARIS_TZ) for dt, _, _ in rows]
    electrical = [elec for _, elec, _ in rows]
    mechanical = [mech for _, _, mech in rows]
    return name, times, electrical, mechanical



def render_station_all(station_id):
    """Render electrical/mechanical availability for a single station over its
    whole recorded history and save it under ``static/history/<uuid>.svg``.

    Returns the path to the written SVG, or None if the station has no data at
    all (so the caller can 404 / show a placeholder).
    """
    name, times, electrical, mechanical = load_station_all(station_id)
    if not times:
        print(f"No data for station {station_id}; skipping all-time chart.")
        return None

    label = name or f"Station {station_id}"

    # With many points, per-point markers turn into noise — drop them past a
    # threshold and let the line carry the shape.
    marker = "o" if len(times) <= 96 else None

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(times, electrical, color=ELECTRICAL, linewidth=1.6, marker=marker,
            markersize=3, label="Electrical")
    ax.plot(times, mechanical, color=MECHANICAL, linewidth=1.6, marker=marker,
            markersize=3, label="Mechanical")

    ax.set_title(f"Bikes available at {label} — all time",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome (matches the city-wide chart).
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.margins(x=0.02)
    ax.set_ylim(bottom=0)

    # Show both the day and the hour so critical (low-availability) times are
    # readable — the daily rhythm is the whole point of the all-time view.
    locator = mdates.AutoDateLocator(tz=PARIS_TZ)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh\n%d/%m", tz=PARIS_TZ))

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=2,
                       columnspacing=1.2)
    legend.set_zorder(6)

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.18)

    os.makedirs(STATION_HISTORY_DIR, exist_ok=True)
    out_path = os.path.join(STATION_HISTORY_DIR, f"{uuid.uuid4()}.svg")
    fig.savefig(out_path, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote station {station_id} all-time chart with {len(times)} points to {out_path}")
    return out_path


def render_station(station_id):
    """Render electrical/mechanical availability for a single station over the
    last 24 hours and save it under ``static/history/<uuid>.svg``.

    Returns the path to the written SVG, or None if the station has no data in
    the window (so the caller can 404 / show a placeholder).
    """
    name, times, electrical, mechanical, max_capacity = load_station_recent(station_id)
    if not times:
        print(f"No data for station {station_id}; skipping chart.")
        return None

    label = name or f"Station {station_id}"

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(times, electrical, color=ELECTRICAL, linewidth=2, marker="o",
            markersize=4, label="Electrical")
    ax.plot(times, mechanical, color=MECHANICAL, linewidth=2, marker="o",
            markersize=4, label="Mechanical")
    # total
    ax.plot(times, [electrical[i] + mechanical[i] for i in range(len(times))],
            color=TOTAL, linewidth=2.4, marker="o", markersize=5, label="Total", zorder=4)
    # The station's parking capacity (total docks) as a dashed ceiling line.
    if max_capacity:
        ax.plot(times, [max_capacity] * len(times), color=MAX_CAPACITY_LINE,
                linewidth=1.2, linestyle="--",
                label=f"Parking capacity ({max_capacity})")


    ax.set_title(f"Bikes available at {label} — last 24 hours",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome (matches the city-wide chart).
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.margins(x=0.02)
    ax.set_ylim(bottom=0)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=PARIS_TZ))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh\n%d/%m", tz=PARIS_TZ))

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=2,
                       columnspacing=1.2)
    legend.set_zorder(6)

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.18)

    os.makedirs(STATION_HISTORY_DIR, exist_ok=True)
    out_path = os.path.join(STATION_HISTORY_DIR, f"{uuid.uuid4()}.svg")
    fig.savefig(out_path, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote station {station_id} chart with {len(times)} points to {out_path}")
    return out_path


def render():
    times, total, electrical, mechanical = load_recent_citywide()
    if not times:
        print("No data to plot; skipping chart.")
        return

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    marker = "o" if len(times) <= 96 else None
    marker_size = 4 if len(times) <= 96 else 0

    ax.plot(times, total, color=TOTAL, linewidth=2.4, marker=marker,
            markersize=marker_size + 1, label="Total", zorder=4)
    ax.plot(times, electrical, color=ELECTRICAL, linewidth=2, marker=marker,
            markersize=marker_size, label="Electrical")
    ax.plot(times, mechanical, color=MECHANICAL, linewidth=2, marker=marker,
            markersize=marker_size, label="Mechanical")

    # Highlight the snapshot with the fewest total bikes over the last 24 hours.
    low_idx = min(range(len(total)), key=lambda i: total[i])
    low_time, low_val = times[low_idx], total[low_idx]
    ax.plot(low_time, low_val, color=LOW, marker="o", markersize=8, zorder=5)
    ax.annotate(f"Lowest total: {int(round(low_val))} at {low_time.strftime('%H:%M')}",
                (low_time, low_val), color=LOW, fontsize=9, fontweight="bold",
                xytext=(0, -16), textcoords="offset points", ha="center")

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=3,
                       columnspacing=1.2)
    legend.set_zorder(6)

    ax.set_title("Bikes available across Lyon — last 24 hours",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome (matches the arrondissement chart).
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.margins(x=0.02)
    ax.set_ylim(bottom=0)

    locator = mdates.AutoDateLocator(tz=PARIS_TZ)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh\n%d/%m", tz=PARIS_TZ))

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.18)

    os.makedirs(ASSETS_DIR, exist_ok=True)
    fig.savefig(CHART_PATH, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote last-24h availability chart with {len(times)} points to {CHART_PATH}")


if __name__ == "__main__":
    render()
