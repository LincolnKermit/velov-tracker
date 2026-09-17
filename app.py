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
    record_visit,
    get_metrics_overview,
)

PARIS_TZ = ZoneInfo("Europe/Paris")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = flask.Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates")
)


def parse_user_agent(ua: str) -> tuple[str, str]:
    """Extract (platform, browser) from User-Agent string."""
    ua_lower = (ua or "").lower()

    if "iphone" in ua_lower or "ipad" in ua_lower:
        platform = "iOS (iPhone/iPad)"
    elif "android" in ua_lower:
        platform = "Android"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        platform = "macOS"
    elif "windows" in ua_lower:
        platform = "Windows"
    elif "linux" in ua_lower:
        platform = "Linux"
    else:
        platform = "Autre"

    if "crios" in ua_lower:
        browser = "Chrome iOS"
    elif "edg" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower and "safari" in ua_lower:
        browser = "Chrome"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "firefox" in ua_lower or "fxios" in ua_lower:
        browser = "Firefox"
    else:
        browser = "Autre"

    return platform, browser


def render_map_page():
    """Render index.html with filesystem fallback and log visit metrics."""
    try:
        ua = flask.request.headers.get("user-agent", "")
        if not any(b in ua.lower() for b in ["bot", "spider", "crawl", "vercel-screenshot", "uptime"]):
            city = flask.request.headers.get("x-vercel-ip-city") or flask.request.headers.get("cf-ipcity") or "Lyon"
            country = flask.request.headers.get("x-vercel-ip-country") or flask.request.headers.get("cf-ipcountry") or "FR"
            platform, browser = parse_user_agent(ua)
            record_visit(city=city, country=country, platform=platform, browser=browser, path="/")
    except Exception as e:
        print(f"[Analytics] Error recording visit: {e}")

    try:
        return flask.render_template("index.html")
    except Exception:
        index_path = os.path.join(BASE_DIR, "templates", "index.html")
        if os.path.isfile(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return flask.Response(f.read(), mimetype="text/html")
        raise


def render_metrics_page():
    """Render metrics.html dashboard."""
    try:
        return flask.render_template("metrics.html")
    except Exception:
        metrics_path = os.path.join(BASE_DIR, "templates", "metrics.html")
        if os.path.isfile(metrics_path):
            with open(metrics_path, "r", encoding="utf-8") as f:
                return flask.Response(f.read(), mimetype="text/html")
        raise


@app.route("/metrics", methods=["GET"])
def metrics_page():
    return render_metrics_page()


@app.route("/api/metrics", methods=["GET"])
@app.route("/api/index/api/metrics", methods=["GET"])
def api_metrics():
    """Return visitor metrics overview (cities, platforms, browsers, total counts)."""
    try:
        data = get_metrics_overview()
        return flask.jsonify(data), 200
    except Exception as e:
        return flask.jsonify({"error": str(e), "total_visits": 0, "cities": {}, "platforms": {}, "browsers": {}}), 500


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    """Catch-all route to handle Vercel rewrites and direct paths reliably."""
    req_path = flask.request.args.get("__path") or path
    clean = req_path.strip("/")
    if clean.startswith("_vercel/insights/script.js"):
        return flask.redirect("https://va.vercel-scripts.com/v1/script.js", code=302)
    if clean.startswith("_vercel/speed-insights/script.js"):
        return flask.redirect("https://va.vercel-scripts.com/v1/speed-insights/script.js", code=302)
    if clean == "metrics" or clean.startswith("metrics/"):
        return render_metrics_page()
    if clean == "api/metrics" or ("metrics" in clean and "api" in clean):
        return api_metrics()
    if "stations" in clean:
        return api_stations()
    if "history" in clean:
        parts = [p for p in clean.split("?")[0].split("/") if p]
        is_all = parts[-1] == "all"
        station_id = parts[-2] if is_all else parts[-1]
        if is_all:
            return history_all(station_id)
        return api_station_history(station_id)
    if clean.startswith("static/"):
        filename = clean[len("static/"):]
        return flask.send_from_directory(app.static_folder, filename)
    return render_map_page()




@app.route("/api/stations", methods=["GET"])
@app.route("/api/index/api/stations", methods=["GET"])
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


def load_recent_history_fallback(station_id, hours=24):
    """Load recent history from data/recent_history.json or api/recent_history.json."""
    candidates = [
        os.path.join(BASE_DIR, "api", "recent_history.json"),
        os.path.join(BASE_DIR, "data", "recent_history.json"),
        "recent_history.json"
    ]
    json_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not json_path:
        return None
    try:
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        station_records = data.get(str(station_id))
        if not station_records:
            return None

        records = []
        for item in station_records:
            if isinstance(item, list) and len(item) >= 6:
                records.append({
                    "timestamp_utc": item[0],
                    "electrical": int(item[1]),
                    "mechanical": int(item[2]),
                    "bikes": int(item[3]),
                    "stands": int(item[4]),
                    "capacity": int(item[5]),
                })
            elif isinstance(item, dict):
                records.append(item)
        return records
    except Exception as e:
        print(f"[Fallback] Error reading recent_history.json: {e}")
        return None


@app.route("/api/history/<station_id>", methods=["GET"])
@app.route("/api/index/api/history/<station_id>", methods=["GET"])
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

    # 2. Try lightweight recent_history.json fallback
    recent_cached = load_recent_history_fallback(station_id, hours=hours)
    if recent_cached:
        capacity = recent_cached[-1].get("capacity", 0) if recent_cached else 0
        return flask.jsonify({
            "station_id": station_id,
            "name": f"Station {station_id}",
            "capacity": capacity,
            "history": recent_cached,
            "source": "recent_history_json"
        })

    # 3. Fallback to full local CSV
    if all_history:
        name, times, electrical, mechanical = load_station_all(station_id)
        capacity = 0
    else:
        name, times, electrical, mechanical, capacity = load_station_recent(station_id)

    if times:
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

    return flask.jsonify({
        "station_id": station_id,
        "name": f"Station {station_id}",
        "capacity": 0,
        "history": [],
        "source": "empty"
    }), 200



@app.route("/history/<station_id>", methods=["GET"])
@app.route("/api/index/history/<station_id>", methods=["GET"])
def history(station_id):
    """Serve SVG chart for last 24h (backwards-compatible route)."""
    svg_path = render_station(station_id)
    if svg_path is None:
        return flask.abort(404, description="No data for this station in the last 24 hours.")
    return flask.send_file(svg_path, mimetype="image/svg+xml")


@app.route("/history/<station_id>/all", methods=["GET"])
@app.route("/api/index/history/<station_id>/all", methods=["GET"])
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