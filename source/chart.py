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
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless: no display in CI
import matplotlib.pyplot as plt

PARIS_TZ = ZoneInfo("Europe/Paris")

CSV_PATH = os.path.join("data", "history.csv")
ASSETS_DIR = "assets"
CHART_PATH = os.path.join(ASSETS_DIR, "availability.svg")

# Palette (validated light surface — reads on both GitHub light and dark themes
# because the image carries its own background).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
TOTAL = "#2a78d6"      # blue    — total bikes
ELECTRICAL = "#007f1c"  # green   — electrical bikes (rgb 0,127,28)
MECHANICAL = "#eb6834"  # orange  — mechanical bikes
LOW = "#d03b3b"        # status critical — marks the lowest total hour


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
