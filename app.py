import os
import flask
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from source.utils import get_stations
from source.chart import render_station, render_station_all, load_station_recent, load_station_all
from source.firebase_db import (
    is_firebase_configured,
    get_latest_stations,
    get_station_history,
    get_station_info,
)

PARIS_TZ = ZoneInfo("Europe/Paris")

app = flask.Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index():
    """Render the main interactive map application."""
    return flask.render_template("index.html")


@app.route("/api/stations", methods=["GET"])
def api_stations():
    """Return latest station availability.

    Queries Firestore first; falls back to JCDecaux live API if Firebase is not yet seeded.
    """
    # 1. Try Firebase Firestore
    if is_firebase_configured():
        latest = get_latest_stations()
        if latest and latest.get("stations"):
            return flask.jsonify(latest)

    # 2. Fallback to direct JCDecaux API call
    try:
        raw_stations = get_stations()
        collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        stations = []
        for s in raw_stations:
            avail = s.get("totalStands", {}).get("availabilities", {})
            stations.append({
                "number": str(s.get("number")),
                "name": s.get("name"),
                "latitude": s.get("position", {}).get("latitude"),
                "longitude": s.get("position", {}).get("longitude"),
                "status": s.get("status"),
                "bikes": int(avail.get("bikes", 0)),
                "electrical": int(avail.get("electricalBikes", 0)),
                "mechanical": int(avail.get("mechanicalBikes", 0)),
                "stands": int(avail.get("stands", 0)),
                "capacity": int(s.get("totalStands", {}).get("capacity", 0)),
                "address": s.get("address", ""),
                "lastUpdate": s.get("lastUpdate", ""),
            })

        return flask.jsonify({
            "timestamp_utc": collected_at,
            "stations_count": len(stations),
            "stations": stations,
            "source": "jcdecaux_live"
        })
    except Exception as e:
        return flask.jsonify({"error": str(e), "stations": []}), 500


@app.route("/api/history/<station_id>", methods=["GET"])
def api_station_history(station_id):
    """Return JSON history for a specific station for Chart.js.

    Query params:
      - hours: number of hours of history (default 24)
      - all: if 'true', returns full history
    """
    station_id = str(station_id)
    all_history = flask.request.args.get("all", "false").lower() == "true"
    hours_arg = flask.request.args.get("hours", "24")
    try:
        hours = int(hours_arg) if not all_history else None
    except ValueError:
        hours = 24

    # 1. Try Firebase first
    if is_firebase_configured():
        info = get_station_info(station_id) or {}
        name = info.get("name", f"Station {station_id}")
        capacity = info.get("capacity", 0)

        history_records = get_station_history(station_id, hours=hours, all_history=all_history)
        if history_records:
            return flask.jsonify({
                "station_id": station_id,
                "name": name,
                "capacity": capacity,
                "history": history_records,
                "source": "firestore"
            })

    # 2. Fallback to CSV
    if all_history:
        name, times, electrical, mechanical = load_station_all(station_id)
        capacity = 0
    else:
        name, times, electrical, mechanical, capacity = load_station_recent(station_id)

    if not times:
        return flask.jsonify({
            "station_id": station_id,
            "name": name or f"Station {station_id}",
            "capacity": capacity,
            "history": [],
            "source": "empty"
        }), 404

    history_records = []
    for t, elec, mech in zip(times, electrical, mechanical):
        utc_str = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        history_records.append({
            "timestamp_utc": utc_str,
            "electrical": elec,
            "mechanical": mech,
            "bikes": elec + mech,
            "stands": max(0, capacity - (elec + mech)) if capacity else 0,
            "capacity": capacity
        })

    return flask.jsonify({
        "station_id": station_id,
        "name": name or f"Station {station_id}",
        "capacity": capacity,
        "history": history_records,
        "source": "csv"
    })


@app.route("/history/<station_id>", methods=["GET"])
def history(station_id):
    """Serve SVG chart for last 24h (backwards-compatible route)."""
    svg_path = render_station(station_id)
    if svg_path is None:
        return flask.abort(404, description="No data for this station in the last 24 hours.")
    return flask.send_file(svg_path, mimetype="image/svg+xml")


@app.route("/history/<station_id>/all", methods=["GET"])
def history_all(station_id):
    """Serve SVG chart for all-time (backwards-compatible route)."""
    svg_path = render_station_all(station_id)
    if svg_path is None:
        return flask.abort(404, description="No data for this station.")
    return flask.send_file(svg_path, mimetype="image/svg+xml")


# Vercel WSGI entry point
# Vercel looks for the `app` variable
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Vélo'v Tracker on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)