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
SERIES = "#2a78d6"     # blue — average line
LOW = "#d03b3b"        # status critical — marks the lowest hour


def load_hourly_profile():
    """Aggregate the CSV into an average city-wide bikes total per hour of day.

    Returns (hours, averages): parallel lists over the local hours (0-23) that
    have at least one snapshot, sorted ascending.
    """
    # For each snapshot timestamp, the city-wide total bikes available.
    per_snapshot = defaultdict(int)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            per_snapshot[row["timestamp_utc"]] += int(row["bikes"])

    # Bucket each snapshot's total by its local hour of day, then average.
    totals = defaultdict(float)
    counts = defaultdict(int)
    for ts, total in per_snapshot.items():
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        hour = dt.astimezone(PARIS_TZ).hour
        totals[hour] += total
        counts[hour] += 1

    hours = sorted(totals)
    averages = [totals[h] / counts[h] for h in hours]
    return hours, averages


def render():
    hours, averages = load_hourly_profile()
    if not hours:
        print("No data to plot; skipping chart.")
        return

    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=100)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(hours, averages, color=SERIES, linewidth=2, marker="o",
            markersize=5, label="Average bikes available")

    # Highlight the hour with the fewest bikes available — the whole point of
    # the chart.
    low_idx = min(range(len(averages)), key=lambda i: averages[i])
    low_hour, low_val = hours[low_idx], averages[low_idx]
    ax.plot(low_hour, low_val, color=LOW, marker="o", markersize=8, zorder=5)
    ax.annotate(f"Lowest: {int(round(low_val))} at {low_hour:02d}h",
                (low_hour, low_val), color=LOW, fontsize=9, fontweight="bold",
                xytext=(0, -16), textcoords="offset points", ha="center")

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
