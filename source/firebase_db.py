import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import credentials, firestore

PARIS_TZ = ZoneInfo("Europe/Paris")

_firestore_client = None
_firebase_initialized = False


def get_firestore_client():
    """Initialize Firebase Admin SDK (if needed) and return Firestore client.

    Supports:
    1. FIREBASE_SERVICE_ACCOUNT (JSON string content, ideal for Vercel/CI)
    2. FIREBASE_CREDENTIALS_PATH / GOOGLE_APPLICATION_CREDENTIALS (file path)
    3. Local file ./serviceAccountKey.json or ./firebase-credentials.json
    4. Default Google Application Credentials (GCP environment)
    """
    global _firestore_client, _firebase_initialized

    if _firestore_client is not None:
        return _firestore_client

    if _firebase_initialized and firebase_admin._apps:
        _firestore_client = firestore.client()
        return _firestore_client

    cred = None

    # 1. Check raw JSON string in environment variable
    raw_service_account = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if raw_service_account:
        try:
            cert_dict = json.loads(raw_service_account)
            cred = credentials.Certificate(cert_dict)
        except Exception as e:
            print(f"[Firebase] Warning: Failed to parse FIREBASE_SERVICE_ACCOUNT JSON: {e}")

    # 2. Check path in environment variable
    if cred is None:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.isfile(cred_path):
            try:
                cred = credentials.Certificate(cred_path)
            except Exception as e:
                print(f"[Firebase] Warning: Failed to load credentials from {cred_path}: {e}")

    # 3. Check default local files
    if cred is None:
        for default_file in ["serviceAccountKey.json", "firebase-credentials.json", ".firebase-credentials.json"]:
            if os.path.isfile(default_file):
                try:
                    cred = credentials.Certificate(default_file)
                    print(f"[Firebase] Using local credentials file: {default_file}")
                    break
                except Exception as e:
                    print(f"[Firebase] Warning: Failed to load credentials from {default_file}: {e}")

    if cred is None:
        return None

    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        _firestore_client = firestore.client()
        return _firestore_client
    except Exception as e:
        print(f"[Firebase] Initialization error: {e}")
        return None


def is_firebase_configured():
    """Return True if Firebase credentials can be found and initialized."""
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if raw or (path and os.path.isfile(path)):
        return get_firestore_client() is not None
    for f in ["serviceAccountKey.json", "firebase-credentials.json", ".firebase-credentials.json"]:
        if os.path.isfile(f):
            return get_firestore_client() is not None
    return False



def arrondissement_of(number):
    """Map station number to Lyon arrondissement (1-9) or None."""
    try:
        n = int(number)
        if 1000 <= n <= 9999:
            return n // 1000
    except (ValueError, TypeError):
        pass
    return None


def save_snapshot(stations, timestamp_utc=None):
    """Save a full snapshot of stations to Firestore.

    Writes:
    1. system/latest_state: all stations and aggregate city stats (for 1-read website loading)
    2. city_snapshots/{timestamp_utc}: citywide aggregates
    3. stations/{station_number}: latest station document
    4. stations/{station_number}/history/{timestamp_utc}: time-series record
    """
    db = get_firestore_client()
    if db is None:
        raise RuntimeError(
            "Firebase is not configured. Set FIREBASE_SERVICE_ACCOUNT or FIREBASE_CREDENTIALS_PATH."
        )

    if timestamp_utc is None:
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_elec = sum(int(s.get("totalStands", {}).get("availabilities", {}).get("electricalBikes", 0)) for s in stations)
    total_mech = sum(int(s.get("totalStands", {}).get("availabilities", {}).get("mechanicalBikes", 0)) for s in stations)
    total_bikes = sum(int(s.get("totalStands", {}).get("availabilities", {}).get("bikes", 0)) for s in stations)
    total_stands = sum(int(s.get("totalStands", {}).get("availabilities", {}).get("stands", 0)) for s in stations)
    open_count = sum(1 for s in stations if s.get("status") == "OPEN")

    arr_elec = {arr: 0 for arr in range(1, 10)}
    for s in stations:
        arr = arrondissement_of(s.get("number"))
        if arr in arr_elec:
            arr_elec[arr] += int(s.get("totalStands", {}).get("availabilities", {}).get("electricalBikes", 0))

    # 1. Update system/latest_state with full station list
    compact_stations = []
    for s in stations:
        avail = s.get("totalStands", {}).get("availabilities", {})
        compact_stations.append({
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

    latest_state_data = {
        "timestamp_utc": timestamp_utc,
        "stations_count": len(stations),
        "total_bikes": total_bikes,
        "electrical": total_elec,
        "mechanical": total_mech,
        "stands": total_stands,
        "open_stations": open_count,
        "by_arrondissement": {str(k): v for k, v in arr_elec.items()},
        "stations": compact_stations,
    }

    db.collection("system").document("latest_state").set(latest_state_data)

    # 2. Write city_snapshots/{timestamp_utc}
    city_snap_data = {
        "timestamp_utc": timestamp_utc,
        "total_bikes": total_bikes,
        "electrical": total_elec,
        "mechanical": total_mech,
        "stands": total_stands,
        "open_stations": open_count,
        "stations_count": len(stations),
        "by_arrondissement": {str(k): v for k, v in arr_elec.items()},
    }
    # Sanitize doc id for Firestore (no slashes)
    safe_ts_id = timestamp_utc.replace(":", "-")
    db.collection("city_snapshots").document(safe_ts_id).set(city_snap_data)

    # 3. Write individual station docs & history entries in batches (max 450 ops per batch)
    batches = []
    current_batch = db.batch()
    op_count = 0

    for s in compact_stations:
        st_num = s["number"]
        st_ref = db.collection("stations").document(st_num)
        hist_ref = st_ref.collection("history").document(safe_ts_id)

        # Update current station doc
        current_batch.set(st_ref, {
            "number": st_num,
            "name": s["name"],
            "latitude": s["latitude"],
            "longitude": s["longitude"],
            "status": s["status"],
            "bikes": s["bikes"],
            "electrical": s["electrical"],
            "mechanical": s["mechanical"],
            "stands": s["stands"],
            "capacity": s["capacity"],
            "address": s["address"],
            "last_update": s["lastUpdate"],
            "timestamp_utc": timestamp_utc,
        }, merge=True)
        op_count += 1

        # Add history entry
        current_batch.set(hist_ref, {
            "timestamp_utc": timestamp_utc,
            "bikes": s["bikes"],
            "electrical": s["electrical"],
            "mechanical": s["mechanical"],
            "stands": s["stands"],
            "capacity": s["capacity"],
            "status": s["status"],
        })
        op_count += 1

        if op_count >= 400:
            batches.append(current_batch)
            current_batch = db.batch()
            op_count = 0

    if op_count > 0:
        batches.append(current_batch)

    for b in batches:
        b.commit()

    print(f"[Firebase] Snapshot saved successfully at {timestamp_utc} ({len(compact_stations)} stations).")


def get_latest_stations():
    """Retrieve the latest station data.

    Returns a dict with 'stations', 'timestamp_utc', and aggregate stats.
    Falls back to None if Firestore is unavailable.
    """
    db = get_firestore_client()
    if db is None:
        return None

    try:
        doc = db.collection("system").document("latest_state").get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"[Firebase] Error reading latest_state: {e}")

    return None


def get_station_history(station_id, hours=24, all_history=False):
    """Retrieve chronological history for a station.

    Returns list of dicts:
    [{'timestamp_utc': '...', 'electrical': int, 'mechanical': int, 'bikes': int, 'stands': int, 'capacity': int}]
    """
    db = get_firestore_client()
    if db is None:
        return None

    station_id = str(station_id)
    try:
        col_ref = db.collection("stations").document(station_id).collection("history")

        if not all_history and hours:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            query = col_ref.where("timestamp_utc", ">=", cutoff).order_by("timestamp_utc")
        else:
            query = col_ref.order_by("timestamp_utc")

        docs = query.stream()
        results = []
        for d in docs:
            data = d.to_dict()
            results.append({
                "timestamp_utc": data.get("timestamp_utc"),
                "electrical": int(data.get("electrical", 0)),
                "mechanical": int(data.get("mechanical", 0)),
                "bikes": int(data.get("bikes", 0)),
                "stands": int(data.get("stands", 0)),
                "capacity": int(data.get("capacity", 0)),
                "status": data.get("status", "OPEN"),
            })

        # Ensure sorted
        results.sort(key=lambda x: x["timestamp_utc"] or "")
        return results
    except Exception as e:
        print(f"[Firebase] Error querying station history for {station_id}: {e}")
        return None


def get_city_snapshots(hours=24):
    """Retrieve citywide snapshots over the last `hours`."""
    db = get_firestore_client()
    if db is None:
        return None

    try:
        col_ref = db.collection("city_snapshots")
        if hours:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            safe_cutoff = cutoff.replace(":", "-")
            query = col_ref.where("__name__", ">=", safe_cutoff).order_by("__name__")
        else:
            query = col_ref.order_by("__name__")

        docs = query.stream()
        results = [d.to_dict() for d in docs]
        results.sort(key=lambda x: x.get("timestamp_utc", ""))
        return results
    except Exception as e:
        print(f"[Firebase] Error querying city snapshots: {e}")
        return None


def get_station_info(station_id):
    """Retrieve metadata for a single station from Firestore."""
    db = get_firestore_client()
    if db is None:
        return None

    try:
        doc = db.collection("stations").document(str(station_id)).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"[Firebase] Error fetching station info for {station_id}: {e}")
    return None


_local_metrics = {
    "total_visits": 0,
    "cities": {},
    "platforms": {},
    "browsers": {},
    "recent_visits": [],
}


def record_visit(city: str, country: str, platform: str, browser: str, path: str = "/"):
    """Record a page visit for analytics (city, platform, browser)."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_city = (city or "Inconnu").strip().title()
    clean_country = (country or "FR").strip().upper()
    clean_platform = (platform or "Autre").strip()
    clean_browser = (browser or "Autre").strip()

    visit_entry = {
        "timestamp_utc": now_iso,
        "city": clean_city,
        "country": clean_country,
        "platform": clean_platform,
        "browser": clean_browser,
        "path": path,
    }

    # Update in-memory metrics
    _local_metrics["total_visits"] += 1
    _local_metrics["cities"][clean_city] = _local_metrics["cities"].get(clean_city, 0) + 1
    _local_metrics["platforms"][clean_platform] = _local_metrics["platforms"].get(clean_platform, 0) + 1
    _local_metrics["browsers"][clean_browser] = _local_metrics["browsers"].get(clean_browser, 0) + 1
    _local_metrics["recent_visits"].insert(0, visit_entry)
    if len(_local_metrics["recent_visits"]) > 50:
        _local_metrics["recent_visits"] = _local_metrics["recent_visits"][:50]

    # If Firestore is configured, persist to database
    db = get_firestore_client()
    if db is not None:
        try:
            doc_ref = db.collection("analytics_metrics").document("overview")
            safe_city = clean_city.replace(".", "_")
            safe_platform = clean_platform.replace(".", "_")
            safe_browser = clean_browser.replace(".", "_")

            doc_ref.set({
                "total_visits": firestore.Increment(1),
                f"cities.{safe_city}": firestore.Increment(1),
                f"platforms.{safe_platform}": firestore.Increment(1),
                f"browsers.{safe_browser}": firestore.Increment(1),
                "last_updated": now_iso,
            }, merge=True)

            db.collection("analytics_visits").add(visit_entry)
        except Exception as e:
            print(f"[Analytics] Warning: Failed to record visit in Firestore: {e}")


def get_metrics_overview():
    """Retrieve metrics overview including total visits, cities, platforms, and recent logs."""
    db = get_firestore_client()
    if db is None:
        return _local_metrics

    try:
        doc = db.collection("analytics_metrics").document("overview").get()
        if not doc.exists:
            return _local_metrics

        data = doc.to_dict() or {}
        recent_docs = db.collection("analytics_visits").order_by("timestamp_utc", direction=firestore.Query.DESCENDING).limit(30).stream()
        recent = [d.to_dict() for d in recent_docs]

        return {
            "total_visits": data.get("total_visits", _local_metrics["total_visits"]),
            "cities": data.get("cities", _local_metrics["cities"]),
            "platforms": data.get("platforms", _local_metrics["platforms"]),
            "browsers": data.get("browsers", _local_metrics["browsers"]),
            "recent_visits": recent or _local_metrics["recent_visits"],
            "last_updated": data.get("last_updated"),
        }
    except Exception as e:
        print(f"[Analytics] Warning: Error fetching metrics from Firestore: {e}")
        return _local_metrics


