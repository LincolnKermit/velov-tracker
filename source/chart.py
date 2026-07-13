"""Render a chart of Vélo'v availability over the last 24 hours from
data/history.csv into assets/availability.svg.

Each snapshot is plotted chronologically (total / electrical / mechanical bikes
available across Lyon), so the line always shows the most recent 24 hours of
movement. The lowest-total point is highlighted.

Run standalone (``python -m source.chart``) or via ``source.collect`` after a
snapshot is appended. The image is regenerated in place every run, so the README
reference to it never needs to change — GitHub serves the fresh file on each
commit.
"""
import csv
import os
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless: no display in CI
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

PARIS_TZ = ZoneInfo("Europe/Paris")

CSV_PATH = os.path.join("data", "history.csv")
ASSETS_DIR = "assets"
CHART_PATH = os.path.join(ASSETS_DIR, "availability.svg")

# Rolling window: only the most recent snapshots are plotted.
WINDOW_HOURS = 24

# Palette (validated light surface — reads on both GitHub light and dark themes
# because the image carries its own background).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
TOTAL = "#2a78d6"      # blue    — total bikes
ELECTRICAL = "#007f1c"  # green   — electrical bikes (rgb 0,127,28)
MECHANICAL = "#eb6834"  # orange  — mechanical bikes
LOW = "#d03b3b"        # status critical — marks the lowest total point


def load_recent():
    """Read the CSV into chronological per-snapshot city-wide totals for the
    last WINDOW_HOURS.

    Returns (times, total, electrical, mechanical): parallel lists sorted by
    time, with times as Europe/Paris datetimes.
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

    cutoff = datetime.now(timezone.utc).timestamp() - WINDOW_HOURS * 3600

    times, total, electrical, mechanical = [], [], [], []
    for ts in sorted(snap_total):
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if dt.timestamp() < cutoff:
            continue
        times.append(dt.astimezone(PARIS_TZ))
        total.append(snap_total[ts])
        electrical.append(snap_elec[ts])
        mechanical.append(snap_mech[ts])

    return times, total, electrical, mechanical


def render():
    times, total, electrical, mechanical = load_recent()
    if not times:
        print("No data to plot; skipping chart.")
        return

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(times, total, color=TOTAL, linewidth=2.4, marker="o",
            markersize=5, label="Total", zorder=4)
    ax.plot(times, electrical, color=ELECTRICAL, linewidth=2, marker="o",
            markersize=4, label="Electrical")
    ax.plot(times, mechanical, color=MECHANICAL, linewidth=2, marker="o",
            markersize=4, label="Mechanical")

    # Highlight the moment the fewest total bikes were available.
    low_idx = min(range(len(total)), key=lambda i: total[i])
    low_t, low_val = times[low_idx], total[low_idx]
    ax.plot(low_t, low_val, color=LOW, marker="o", markersize=8, zorder=5)
    ax.annotate(f"Lowest: {low_val} at {low_t.strftime('%Hh%M')}",
                (low_t, low_val), color=LOW, fontsize=9, fontweight="bold",
                xytext=(0, -16), textcoords="offset points", ha="center")

    ax.set_title("Bikes available across Lyon — last 24 hours",
                 color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)

    # Recessive chrome.
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

    legend = ax.legend(loc="lower left", frameon=False, fontsize=9,
                       labelcolor=INK, handlelength=1.4, ncol=3,
                       columnspacing=1.2)
    legend.set_zorder(6)

    fig.subplots_adjust(left=0.06, right=0.97, top=0.86, bottom=0.18)

    os.makedirs(ASSETS_DIR, exist_ok=True)
    fig.savefig(CHART_PATH, format="svg", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote last-24h chart with {len(times)} points to {CHART_PATH}")


if __name__ == "__main__":
    render()
