"""Render a chart of average Vélo'v availability by hour of day from
data/history.csv into assets/availability.svg.

Every hourly snapshot is bucketed by its local (Europe/Paris) hour and the
city-wide total bikes available is averaged across all collected days, giving a
typical 24-hour profile — so you can see at which hours the fewest bikes are
available.

Run standalone (``python -m source.chart``) or via ``source.collect`` after a
snapshot is appended. The image is regenerated in place every run, so the README
reference to it never needs to change — GitHub serves the fresh file on each
commit.
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
TOTAL = "#2a78d6"      # blue    — total bikes
ELECTRICAL = "#007f1c"  # green   — electrical bikes (rgb 0,127,28)
MECHANICAL = "#eb6834"  # orange  — mechanical bikes
LOW = "#d03b3b"        # status critical — marks the lowest total point

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

    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_HOURS * 3600

    times = []
    series = {arr: [] for arr in sorted(ARR_COLORS)}
    for ts in sorted(snap):
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
    """Read the CSV into chronological electrical/mechanical availability for a
    single station over the last WINDOW_HOURS.

    Returns (name, times, electrical, mechanical): the station's display name
    and three parallel lists sorted by time, with times as Europe/Paris
    datetimes.
    """
    station_id = str(station_id)
    name = None
    rows = []  # (utc datetime, electrical, mechanical)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["number"] != station_id:
                continue
            name = row["name"]
            dt = datetime.strptime(row["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            rows.append((dt, int(row["electrical"]), int(row["mechanical"])))

    if not rows:
        return name, [], [], []

    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_HOURS * 3600
    rows.sort(key=lambda r: r[0])

    times, electrical, mechanical = [], [], []
    for dt, elec, mech in rows:
        if dt.timestamp() < cutoff:
            continue
        times.append(dt.astimezone(PARIS_TZ))
        electrical.append(elec)
        mechanical.append(mech)

    return name, times, electrical, mechanical


def render_station(station_id):
    """Render electrical/mechanical availability for a single station over the
    last 24 hours and save it under ``static/history/<uuid>.svg``.

    Returns the path to the written SVG, or None if the station has no data in
    the window (so the caller can 404 / show a placeholder).
    """
    name, times, electrical, mechanical = load_station_recent(station_id)
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
    hours, total, electrical, mechanical = load_hourly_profile()
    if not hours:
        print("No data to plot; skipping chart.")
        return

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(hours, total, color=TOTAL, linewidth=2.4, marker="o",
            markersize=5, label="Total", zorder=4)
    ax.plot(hours, electrical, color=ELECTRICAL, linewidth=2, marker="o",
            markersize=4, label="Electrical")
    ax.plot(hours, mechanical, color=MECHANICAL, linewidth=2, marker="o",
            markersize=4, label="Mechanical")

    # Highlight the hour with the fewest total bikes — the whole point of the
    # chart.
    low_idx = min(range(len(total)), key=lambda i: total[i])
    low_hour, low_val = hours[low_idx], total[low_idx]
    ax.plot(low_hour, low_val, color=LOW, marker="o", markersize=8, zorder=5)
    ax.annotate(f"Lowest total: {int(round(low_val))} at {low_hour:02d}h",
                (low_hour, low_val), color=LOW, fontsize=9, fontweight="bold",
                xytext=(0, -16), textcoords="offset points", ha="center")

    legend = ax.legend(loc="upper right", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=3,
                       columnspacing=1.2)
    legend.set_zorder(6)

    ax.set_title("Average bikes available across Lyon, by hour of day",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome.
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_ylim(bottom=0)

    # Full 24-hour axis so the daily rhythm is always framed the same way.
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.15)

    os.makedirs(ASSETS_DIR, exist_ok=True)
    fig.savefig(CHART_PATH, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote hourly profile with {len(hours)} hours to {CHART_PATH}")


if __name__ == "__main__":
    render()
