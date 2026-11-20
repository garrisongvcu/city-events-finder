import os
from typing import Optional
import re
import requests
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")
PREDICTHQ_API_KEY = os.getenv("PREDICTHQ_API_KEY", "")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Richmond")


def parse_location(query: str):
    """Splits 'Richmond, VA' or 'Richmond' into (city, state_code)."""
    parts = [p.strip() for p in query.split(",")]
    city = parts[0] if parts and parts[0] else DEFAULT_CITY
    state = parts[1].upper() if len(parts) > 1 and len(parts[1]) == 2 else ""
    return city, state


def normalize_title(title: str) -> str:
    """Normalizes event titles for duplicate detection."""
    cleaned = re.sub(r"[^a-z0-9\s]", "", title.lower())
    return " ".join(cleaned.split())


def geocode_city(city: str, state: str):
    """Resolves city/state into latitude, longitude, and label via Open-Meteo."""
    geo_resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 5, "language": "en", "format": "json"},
        timeout=5,
    ).json()
    locations = geo_resp.get("results", [])
    if not locations:
        return None

    chosen = locations[0]
    for loc in locations:
        if loc.get("country_code") == "US":
            if not state or state.lower() in loc.get("admin1", "").lower():
                chosen = loc
                break

    return {
        "lat": chosen["latitude"],
        "lon": chosen["longitude"],
        "label": f"{chosen.get('name')}, {chosen.get('admin1', '')}",
    }


def fetch_ticketmaster_events(city: str, state: str):
    """Event Source 1: Ticketmaster Discovery API (active once key is approved)."""
    if not TICKETMASTER_API_KEY or TICKETMASTER_API_KEY == "your_ticketmaster_key_here":
        return []
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "city": city,
        "size": 15,
        "sort": "date,asc",
    }
    if state:
        params["stateCode"] = state

    try:
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        raw_events = resp.json().get("_embedded", {}).get("events", [])
        results = []
        for ev in raw_events:
            dates = ev.get("dates", {}).get("start", {})
            date_str = dates.get("dateTime") or f"{dates.get('localDate', '')}T00:00:00Z"
            venues = ev.get("_embedded", {}).get("venues", [{}])
            venue_name = venues[0].get("name", "TBA")
            results.append({
                "title": ev.get("name", "Untitled Event"),
                "date_iso": date_str,
                "local_date": dates.get("localDate", "TBA"),
                "local_time": dates.get("localTime", "")[:5],
                "venue": venue_name,
                "url": ev.get("url", "#"),
                "source": "Ticketmaster",
            })
        return results
    except Exception as e:
        app.logger.error(f"Ticketmaster error: {e}")
        return []


def fetch_predicthq_events(geo: Optional[dict]):
    """Event Source 2: PredictHQ Events API."""
    if not PREDICTHQ_API_KEY or PREDICTHQ_API_KEY == "your_predicthq_key_here" or not geo:
        return []
    url = "https://api.predicthq.com/v1/events/"
    headers = {
        "Authorization": f"Bearer {PREDICTHQ_API_KEY}",
        "Accept": "application/json",
    }
    params = {
        "within": f"20mi@{geo['lat']},{geo['lon']}",
        "limit": 15,
        "sort": "start",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=6)
        resp.raise_for_status()
        raw_events = resp.json().get("results", [])
        results = []
        for ev in raw_events:
            start_str = ev.get("start", "")
            local_date = start_str.split("T")[0] if "T" in start_str else (start_str or "TBA")
            local_time = start_str.split("T")[1][:5] if "T" in start_str else ""
            entities = ev.get("entities", [])
            venue_name = entities[0].get("name", "Local Venue") if entities else "Local Venue"
            results.append({
                "title": ev.get("title", "Untitled Event"),
                "date_iso": start_str or "9999-12-31T23:59:59",
                "local_date": local_date,
                "local_time": local_time,
                "venue": venue_name,
                "url": "#",
                "source": "PredictHQ",
            })
        return results
    except Exception as e:
        app.logger.error(f"PredictHQ error: {e}")
        return []


def fetch_weather(geo: Optional[dict]):
    """Enrichment Source 3: Open-Meteo Forecast (no API key needed)."""
    if not geo:
        return None
    try:
        w_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": geo["lat"],
                "longitude": geo["lon"],
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "forecast_days": 5,
            },
            timeout=5,
        ).json()

        return {
            "location_label": geo["label"],
            "current": w_resp.get("current", {}),
            "daily": w_resp.get("daily", {}),
        }
    except Exception as e:
        app.logger.error(f"Open-Meteo error: {e}")
        return None


def merge_and_deduplicate(events: list) -> list:
    """Deduplicates by normalized title + local_date, then sorts soonest first."""
    seen = {}
    for ev in events:
        dedup_key = (normalize_title(ev["title"]), ev["local_date"])
        if dedup_key not in seen:
            seen[dedup_key] = ev
        elif ev["source"] not in seen[dedup_key]["source"]:
            seen[dedup_key]["source"] += f" & {ev['source']}"
    return sorted(seen.values(), key=lambda x: x["date_iso"])


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "").strip()
    events = []
    weather = None

    if query:
        city, state = parse_location(query)
        geo = geocode_city(city, state)
        tm_events = fetch_ticketmaster_events(city, state)
        phq_events = fetch_predicthq_events(geo)
        events = merge_and_deduplicate(tm_events + phq_events)
        weather = fetch_weather(geo)

    return render_template("index.html", query=query, events=events, weather=weather)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
