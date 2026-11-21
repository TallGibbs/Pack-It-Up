"""Real-time Point A -> Point B truck route intelligence, city parking & calm move support.

Pulls live real-time data from public geo/weather/traffic endpoints (with an injectable
`LiveRouteDataClient` for deterministic offline tests and instant fallback profiles) and
synthesizes concise, non-overbearing guidance with Gemini 4 (`for_job("route")`) and the
Gemini Decisions API (`for_job("decide")`, `gemini-decision-1`):

  1. Live geocoding & urban density detection (OpenStreetMap Nominatim + NYC/US presets)
  2. Live street-by-street route & passenger-car trap detection (OSRM routing steps)
  3. Live bridge clearance (`maxheight`), `hgv=no`, and `toll=yes` scan (OSM Overpass)
  4. Live weather, precipitation & bridge crosswind gusts at Point A & B (Open-Meteo)
  5. Live NYC DOT corridor sensor speeds (`data.cityofnewyork.us` real-time traffic feed)
  6. Truck-mode phone navigation reminder (Hammer / Trucker Path / CoPilot vs Google/Apple/Waze)
  7. Tolls, E-ZPass vs rental plate-billing traps, and city curb/loading parking tips

Note: Per `AGENTS.md`, no model SDK is imported here; all model calls go through `backend.llm`.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from backend import catalog
from backend.llm import LLMError, _load_env, for_job

ROOT = Path(__file__).resolve().parents[1]
ROUTE_CACHE_DIR = ROOT / ".cache" / "route_live"
USER_AGENT = "PackItUp-MoveAssistant/1.0 (Gemini4-NYC-Hackathon)"

DEFAULT_ORIGIN = "The Malin SoHo, 387 Broadway, New York, NY 10013"
DEFAULT_DESTINATION = "NY Penn Station, 234 W 31st St, New York, NY 10001"

# Instant high-precision presets so common demo / NYC / Tri-State addresses resolve
# immediately even on restricted venue Wi-Fi, while live Nominatim handles any address.
KNOWN_PLACES: list[dict[str, Any]] = [
    {
        "match": ["malin soho", "387 broadway"],
        "label": "The Malin SoHo, 387 Broadway, New York, NY 10013",
        "lat": 40.7186,
        "lon": -74.0018,
        "city": "New York",
        "borough": "Manhattan",
        "neighborhood": "SoHo / Tribeca",
        "state": "NY",
        "postal_code": "10013",
        "urban_tier": "dense_city",
    },
    {
        "match": ["malin flatiron", "18 w 21st", "flatiron"],
        "label": "The Malin Flatiron, 18 W 21st St, New York, NY 10010",
        "lat": 40.7405,
        "lon": -73.9926,
        "city": "New York",
        "borough": "Manhattan",
        "neighborhood": "Flatiron",
        "state": "NY",
        "postal_code": "10010",
        "urban_tier": "dense_city",
    },
    {
        "match": ["penn station", "moynihan", "234 w 31st", "8th ave & w 31st", "pennsylvania station"],
        "label": "NY Penn Station, 234 W 31st St, New York, NY 10001",
        "lat": 40.7506,
        "lon": -73.9935,
        "city": "New York",
        "borough": "Manhattan",
        "neighborhood": "Midtown West / Penn District",
        "state": "NY",
        "postal_code": "10001",
        "urban_tier": "dense_city",
    },
    {
        "match": ["williamsburg", "bedford ave", "brooklyn"],
        "label": "Williamsburg, Bedford Ave, Brooklyn, NY 11211",
        "lat": 40.7178,
        "lon": -73.9577,
        "city": "New York",
        "borough": "Brooklyn",
        "neighborhood": "Williamsburg",
        "state": "NY",
        "postal_code": "11211",
        "urban_tier": "dense_city",
    },
    {
        "match": ["astoria", "long island city", "lic", "queens"],
        "label": "Long Island City, Queens, NY 11101",
        "lat": 40.7447,
        "lon": -73.9485,
        "city": "New York",
        "borough": "Queens",
        "neighborhood": "Long Island City",
        "state": "NY",
        "postal_code": "11101",
        "urban_tier": "dense_city",
    },
    {
        "match": ["hoboken", "jersey city", "newark ave", "washington st, hoboken"],
        "label": "Hoboken, Washington St, NJ 07030",
        "lat": 40.7433,
        "lon": -74.0324,
        "city": "Hoboken",
        "borough": "",
        "neighborhood": "Downtown Hoboken",
        "state": "NJ",
        "postal_code": "07030",
        "urban_tier": "dense_city",
    },
    {
        "match": ["upper west side", "columbus ave", "amsterdam ave", "uws"],
        "label": "Upper West Side, W 79th St, New York, NY 10024",
        "lat": 40.7831,
        "lon": -73.9772,
        "city": "New York",
        "borough": "Manhattan",
        "neighborhood": "Upper West Side",
        "state": "NY",
        "postal_code": "10024",
        "urban_tier": "dense_city",
    },
]

DENSE_US_CITIES = {
    "new york", "manhattan", "brooklyn", "queens", "bronx", "staten island",
    "jersey city", "hoboken", "newark", "boston", "cambridge", "somerville",
    "philadelphia", "washington", "chicago", "san francisco", "oakland",
    "los angeles", "seattle", "miami", "atlanta", "baltimore", "pittsburgh",
}

# Known truck-banned parkways, bridges, and restricted tunnels matched against live OSRM road steps
# OR corridor bounding boxes so we catch consumer-GPS routing traps reliably.
KNOWN_NO_TRUCK_CORRIDORS: list[dict[str, Any]] = [
    {
        "patterns": ["fdr", "franklin d. roosevelt", "east river dr"],
        "road": "FDR Drive (East Side Parkway)",
        "rule": "Zero commercial or rental box trucks allowed (low 9'–11' overpasses & parkway law).",
        "safe_alt": "Use 1st Ave (uptown), 2nd Ave (downtown), or 3rd Ave Local Truck Routes.",
    },
    {
        "patterns": ["henry hudson", "9a", "west side hwy", "miller hwy"],
        "road": "Henry Hudson Parkway (north of W 59th St)",
        "rule": "Box trucks strictly prohibited north of 59th St. Note: Route 9A / 11th–12th Ave south of 59th St allows surface truck travel.",
        "safe_alt": "North of 59th St use Amsterdam Ave, Broadway, or I-95; south of 59th St stay on 11th/12th Ave or 8th/9th/10th Ave.",
    },
    {
        "patterns": ["brooklyn bridge"],
        "road": "Brooklyn Bridge",
        "rule": "All commercial & rental box trucks are banned on the Brooklyn Bridge (10'–11' clearance & weight limit).",
        "safe_alt": "Cross via Manhattan Bridge (lower roadway) or Williamsburg Bridge (outer roadways).",
    },
    {
        "patterns": ["holland tunnel", "i-78"],
        "road": "Holland Tunnel",
        "rule": "Port Authority bans wider/heavier multi-axle box trucks and enforces strict 12'0\" height gauges.",
        "safe_alt": "Take the Lincoln Tunnel (13'0\" clearance, puts you right at W 30th–40th St near Penn Station) or GW Bridge Upper Level.",
    },
    {
        "patterns": ["belt pkwy", "belt parkway", "shore pkwy"],
        "road": "Belt Parkway / Shore Parkway",
        "rule": "NY State Parkway: all box trucks & commercial plates/rentals prohibited (bridges as low as 9'0\").",
        "safe_alt": "Use I-278 (BQE / Gowanus Expy) or Atlantic Ave / Flatbush Ave truck routes.",
    },
    {
        "patterns": ["grand central", "jackie robinson", "cross island", "hutchinson", "saw mill", "taconic", "sprain brook", "northern state", "southern state"],
        "road": "NY Metro Parkways (Grand Central / Jackie Robinson / Hutchinson / Taconic)",
        "rule": "Every road named 'Parkway' in NY bans rental moving trucks—even on a regular driver's license.",
        "safe_alt": "Stay on 'Expressways' or 'Thruways' (I-495 LIE, I-278 BQE, I-95, I-87).",
    },
    {
        "patterns": ["merritt", "wilbur cross", "ct-15", "route 15"],
        "road": "Merritt / Wilbur Cross Parkway (CT-15)",
        "rule": "Famous arched stone bridges (as low as 8'6\"–10'0\"); all trucks & trailers prohibited.",
        "safe_alt": "Take I-95 or I-84 through Connecticut.",
    },
    {
        "patterns": ["storrow", "soldiers field", "memorial dr"],
        "road": "Storrow Drive / Memorial Drive (Boston/Cambridge)",
        "rule": "Notorious 'Storrowing' 10'0\" bridges—instant roof peel for box trucks.",
        "safe_alt": "Use I-90 (Mass Pike) or Massachusetts Ave / Monsignor O'Brien Hwy.",
    },
    {
        "patterns": ["lake shore", "dusable"],
        "road": "DuSable Lake Shore Drive (Chicago)",
        "rule": "Trucks and commercial moving vans are prohibited along Lake Shore Drive.",
        "safe_alt": "Use I-90 / I-94 (Kennedy / Dan Ryan Expressway) or Ashland / Western Ave.",
    },
]

NAV_APP_PROFILES: dict[str, dict[str, Any]] = {
    "hammer": {
        "id": "hammer",
        "name": "Hammer Truck GPS",
        "has_native_truck_mode": True,
        "badge": "True Commercial Truck Mode (Free)",
        "how_to_enable": "Tap the Truck icon → Vehicle Dimensions → set Height, Length & Weight, and toggle Commercial Vehicle ON before tapping Go.",
        "watchout": "Double-check your last-block turn onto local streets so you approach your building's curb on the right-hand side.",
    },
    "trucker_path": {
        "id": "trucker_path",
        "name": "Trucker Path",
        "has_native_truck_mode": True,
        "badge": "True Commercial Truck Mode",
        "how_to_enable": "Open Settings → Truck Profile → enter exact exterior height (plus 6\" buffer), total length, and 2-axle box truck.",
        "watchout": "Automatically routes around NY/CT/MA parkways and low railroad underpasses.",
    },
    "copilot": {
        "id": "copilot",
        "name": "CoPilot GPS / Sygic Truck",
        "has_native_truck_mode": True,
        "badge": "True Commercial Truck Mode",
        "how_to_enable": "Select Light/Medium Commercial Truck routing profile and enter your U-Haul roof clearance and GVWR.",
        "watchout": "Works offline in tunnels where cell GPS drops out.",
    },
    "google_maps": {
        "id": "google_maps",
        "name": "Google Maps",
        "has_native_truck_mode": False,
        "badge": "Passenger Car Only — No Truck Mode!",
        "how_to_enable": "Google Maps has NO commercial truck or bridge-height mode on phones. Switch to Hammer or Trucker Path for the drive, or manually verify every highway against the No-Truck list below (and check Route Options → Avoid Tolls if desired).",
        "watchout": "Google Maps WILL route a 12'0\" U-Haul onto FDR Drive, Brooklyn Bridge, Belt Pkwy, or Storrow Dr if you follow its default blue line.",
    },
    "apple_maps": {
        "id": "apple_maps",
        "name": "Apple Maps",
        "has_native_truck_mode": False,
        "badge": "Passenger Car Only — No Truck Mode!",
        "how_to_enable": "Apple Maps does NOT filter low bridges or truck-prohibited parkways. Use a truck-aware GPS app (Hammer / Trucker Path) for highway routing, or inspect each turn against the restricted-road list here.",
        "watchout": "Great for checking street-level building entrances on foot, unsafe as your sole highway guide in a box truck.",
    },
    "waze": {
        "id": "waze",
        "name": "Waze",
        "has_native_truck_mode": False,
        "badge": "Passenger Car / Taxi Only — No Truck Mode!",
        "how_to_enable": "Waze only offers Private Car, Taxi, and Motorcycle—no Commercial Truck or height clearance setting. Do not take Waze cut-throughs in a box truck; pair with Hammer or stick to designated truck avenues.",
        "watchout": "Waze aggressively detours down narrow residential side streets, tight alleys, and parkways during traffic.",
    },
}

WMO_WEATHER_LABELS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Moderate showers",
    82: "Heavy showers",
    95: "Thunderstorm",
}

ROUTE_SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "calm_headline",
        "route_summary",
        "toll_tips",
        "no_truck_tips",
        "nav_mode_tip",
        "city_parking_tips",
        "gentle_stage_nudges",
    ],
    "properties": {
        "calm_headline": {"type": "string"},
        "route_summary": {"type": "string"},
        "toll_tips": {"type": "array", "items": {"type": "string"}},
        "no_truck_tips": {"type": "array", "items": {"type": "string"}},
        "nav_mode_tip": {"type": "string"},
        "city_parking_tips": {"type": "array", "items": {"type": "string"}},
        "gentle_stage_nudges": {
            "type": "object",
            "required": ["pack", "load", "drive", "park_unload", "unpack"],
            "properties": {
                "pack": {"type": "string"},
                "load": {"type": "string"},
                "drive": {"type": "string"},
                "park_unload": {"type": "string"},
                "unpack": {"type": "string"},
            },
        },
    },
}

_cache_lock = threading.Lock()


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_height_to_inches(raw: str | None) -> float | None:
    """Parse OSM `maxheight` values like `3.6`, `3.6 m`, `11'4"`, `10 ft 6 in` into inches."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s in ("default", "none", "below_default"):
        return None
    # Feet and inches: 11'4", 11' 4", 11 ft 4 in, 12'
    m_ft = re.search(r"(\d{1,2})\s*(?:'|ft|feet)\s*(\d{1,2})?", s)
    if m_ft:
        ft = int(m_ft.group(1))
        inch = int(m_ft.group(2) or 0)
        return float(ft * 12 + inch)
    # Meters: 3.65, 3.65 m
    m_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|meters|metres)?$", s)
    if m_m:
        val = float(m_m.group(1))
        if 1.5 <= val <= 8.0:
            return round(val * 39.3701, 1)
    return None


def fmt_inches_ft(inches: float) -> str:
    total = int(round(inches))
    return f"{total // 12}' {total % 12}\""


def _is_nyc_metro(lat: float, lon: float) -> bool:
    return 40.48 <= lat <= 41.05 and -74.30 <= lon <= -73.65


def _is_manhattan_crz(lat: float, lon: float) -> bool:
    """Roughly Manhattan south of 60th Street (Congestion Relief Zone)."""
    return 40.700 <= lat <= 40.768 and -74.020 <= lon <= -73.968


class LiveRouteDataClient:
    """Fetches real-time geocoding, routing, OSM truck restrictions, weather, and NYC traffic."""

    def __init__(self, use_cache: bool = True, cache_ttl_s: int = 300, timeout_s: float = 5.5):
        self.use_cache = use_cache
        self.cache_ttl_s = cache_ttl_s
        self.timeout_s = timeout_s

    def _cache_read(self, key: str) -> Any | None:
        if not self.use_cache:
            return None
        p = ROUTE_CACHE_DIR / f"{key}.json"
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if time.time() - float(obj.get("ts", 0)) <= self.cache_ttl_s:
                return obj.get("data")
        except Exception:
            return None
        return None

    def _cache_write(self, key: str, data: Any) -> None:
        if not self.use_cache:
            return
        try:
            ROUTE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = ROUTE_CACHE_DIR / f"{key}.{threading.get_ident()}.tmp"
            tmp.write_text(json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
            with _cache_lock:
                os.replace(tmp, ROUTE_CACHE_DIR / f"{key}.json")
        except Exception:
            pass

    def _http_get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_post_form_json(self, url: str, form: dict[str, str]) -> Any:
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def geocode(self, address: str) -> dict[str, Any]:
        clean = (address or "").strip() or DEFAULT_ORIGIN
        low = clean.lower()

        # Check high-precision local match first as fallback seed, still enrich live when possible
        preset_hit: dict[str, Any] | None = None
        for p in KNOWN_PLACES:
            if any(tok in low for tok in p["match"]):
                preset_hit = dict(p)
                break

        ck = "geo_" + hashlib.sha256(low.encode("utf-8")).hexdigest()[:20]
        cached = self._cache_read(ck)
        if cached:
            return {**cached, "cached": True}

        try:
            q = urllib.parse.urlencode({"q": clean, "format": "jsonv2", "addressdetails": "1", "limit": "1"})
            rows = self._http_get_json(f"https://nominatim.openstreetmap.org/search?{q}")
            if isinstance(rows, list) and rows:
                r = rows[0]
                addr = r.get("address") or {}
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("borough")
                    or addr.get("suburb")
                    or addr.get("county")
                    or ""
                )
                borough = addr.get("borough") or addr.get("city_district") or addr.get("suburb") or ""
                state = addr.get("state") or ""
                postcode = addr.get("postcode") or ""
                lat = float(r["lat"])
                lon = float(r["lon"])
                city_Check = f"{city} {borough}".lower()
                is_city = (
                    any(dc in city_Check for dc in DENSE_US_CITIES)
                    or r.get("addresstype") in ("building", "amenity", "commercial", "retail", "railway")
                    or _is_nyc_metro(lat, lon)
                )
                out = {
                    "query": clean,
                    "label": r.get("display_name") or clean,
                    "short_label": ", ".join(x for x in [borough or city, state] if x) or clean[:48],
                    "lat": lat,
                    "lon": lon,
                    "city": city,
                    "borough": borough,
                    "neighborhood": addr.get("neighbourhood") or addr.get("quarter") or borough,
                    "state": state,
                    "postal_code": postcode,
                    "urban_tier": "dense_city" if is_city else "suburban",
                    "source": "nominatim_live",
                }
                self._cache_write(ck, out)
                return out
        except Exception:
            pass

        if preset_hit:
            return {
                "query": clean,
                "label": preset_hit["label"],
                "short_label": f"{preset_hit.get('neighborhood') or preset_hit['city']}, {preset_hit['state']}",
                "lat": preset_hit["lat"],
                "lon": preset_hit["lon"],
                "city": preset_hit["city"],
                "borough": preset_hit.get("borough", ""),
                "neighborhood": preset_hit.get("neighborhood", ""),
                "state": preset_hit["state"],
                "postal_code": preset_hit["postal_code"],
                "urban_tier": preset_hit["urban_tier"],
                "source": "preset_fallback",
            }

        # Generic city-keyword fallback if offline with an unseen address
        looks_urban = any(c in low for c in DENSE_US_CITIES) or bool(re.search(r"\b(apt|suite|ave|st|blvd|ny\s*10\d{3})\b", low))
        return {
            "query": clean,
            "label": clean,
            "short_label": clean[:44],
            "lat": 40.7350,
            "lon": -73.9950,
            "city": "New York" if "ny" in low else "",
            "borough": "Manhattan" if "100" in low or "new york" in low else "",
            "neighborhood": "",
            "state": "NY" if "ny" in low else "",
            "postal_code": "",
            "urban_tier": "dense_city" if looks_urban else "suburban",
            "source": "heuristic_fallback",
        }

    def fetch_osrm_route(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        lat1, lon1 = float(orig["lat"]), float(orig["lon"])
        lat2, lon2 = float(dest["lat"]), float(dest["lon"])
        coord_key = f"osrm_{lat1:.4f}_{lon1:.4f}_{lat2:.4f}_{lon2:.4f}"
        cached = self._cache_read(coord_key)
        if cached:
            return {**cached, "cached": True}

        try:
            url = (
                f"https://router.project-osrm.org/route/v1/driving/"
                f"{lon1:.5f},{lat1:.5f};{lon2:.5f},{lat2:.5f}"
                f"?overview=simplified&geometries=geojson&steps=true&alternatives=true"
            )
            data = self._http_get_json(url)
            routes = data.get("routes") or []
            if routes:
                primary = routes[0]
                dist_mi = round(float(primary.get("distance", 0.0)) / 1609.344, 1)
                dur_min = max(3, int(round(float(primary.get("duration", 0.0)) / 60.0)))

                road_names: list[str] = []
                seen_roads: set[str] = set()
                alt_road_names: list[str] = []

                for r_idx, rt in enumerate(routes):
                    for leg in rt.get("legs") or []:
                        for st in leg.get("steps") or []:
                            nm = " ".join(x for x in [st.get("name"), st.get("ref")] if x).strip()
                            if not nm:
                                continue
                            norm = nm.lower()
                            if r_idx == 0:
                                if norm not in seen_roads:
                                    seen_roads.add(norm)
                                    road_names.append(nm)
                            elif norm not in seen_roads and nm not in alt_road_names:
                                alt_road_names.append(nm)

                coords = (primary.get("geometry") or {}).get("coordinates") or [[lon1, lat1], [lon2, lat2]]
                out = {
                    "distance_miles": max(0.2, dist_mi),
                    "car_duration_min": dur_min,
                    "roads_on_primary": road_names[:24],
                    "roads_on_alternatives": alt_road_names[:16],
                    "sampled_coords": coords[:: max(1, len(coords) // 8)][:10],
                    "source": "osrm_live",
                }
                self._cache_write(coord_key, out)
                return out
        except Exception:
            pass

        crow_mi = max(0.4, _haversine_miles(lat1, lon1, lat2, lon2))
        est_mi = round(crow_mi * 1.32, 1)
        est_min = max(8, int(round((est_mi / 16.0) * 60.0)))
        return {
            "distance_miles": est_mi,
            "car_duration_min": est_min,
            "roads_on_primary": [],
            "roads_on_alternatives": [],
            "sampled_coords": [[lon1, lat1], [(lon1 + lon2) / 2, (lat1 + lat2) / 2], [lon2, lat2]],
            "source": "distance_fallback",
        }

    def fetch_overpass_restrictions(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        lat1, lon1 = float(orig["lat"]), float(orig["lon"])
        lat2, lon2 = float(dest["lat"]), float(dest["lon"])
        # Keep Overpass bounding box tight so live queries finish in <2.5s; skip giant cross-country boxes
        if _haversine_miles(lat1, lon1, lat2, lon2) > 35.0:
            return {"low_clearances": [], "hgv_bans": [], "toll_points": [], "source": "corridor_too_wide_skipped"}

        south = min(lat1, lat2) - 0.012
        north = max(lat1, lat2) + 0.012
        west = min(lon1, lon2) - 0.012
        east = max(lon1, lon2) + 0.012
        ck = f"ovp_{south:.3f}_{west:.3f}_{north:.3f}_{east:.3f}"
        cached = self._cache_read(ck)
        if cached:
            return {**cached, "cached": True}

        query = (
            f"[out:json][timeout:4];("
            f'way["maxheight"]({south:.4f},{west:.4f},{north:.4f},{east:.4f});'
            f'way["hgv"="no"]["highway"~"motorway|trunk|primary"]({south:.4f},{west:.4f},{north:.4f},{east:.4f});'
            f'way["toll"="yes"]["highway"~"motorway|trunk|primary"]({south:.4f},{west:.4f},{north:.4f},{east:.4f});'
            f");out tags 45;"
        )
        try:
            res = self._http_post_form_json("https://overpass-api.de/api/interpreter", {"data": query})
            low_clearances: list[dict[str, Any]] = []
            hgv_bans: list[str] = []
            toll_points: list[str] = []
            seen_lc: set[str] = set()

            for el in res.get("elements") or []:
                tags = el.get("tags") or {}
                name = tags.get("name") or tags.get("ref") or ""
                mh = tags.get("maxheight")
                if mh:
                    inches = parse_height_to_inches(mh)
                    key = f"{name}:{mh}"
                    if inches and key not in seen_lc:
                        seen_lc.add(key)
                        low_clearances.append({
                            "name": name or "Corridor overpass / bridge",
                            "raw_maxheight": mh,
                            "clearance_in": inches,
                            "clearance_label": fmt_inches_ft(inches),
                        })
                if tags.get("hgv") == "no" and name and name not in hgv_bans:
                    hgv_bans.append(name)
                if tags.get("toll") == "yes" and name and name not in toll_points:
                    toll_points.append(name)

            low_clearances.sort(key=lambda x: x["clearance_in"])
            out = {
                "low_clearances": low_clearances[:8],
                "hgv_bans": hgv_bans[:10],
                "toll_points": toll_points[:8],
                "source": "overpass_live",
            }
            self._cache_write(ck, out)
            return out
        except Exception:
            return {"low_clearances": [], "hgv_bans": [], "toll_points": [], "source": "overpass_unavailable"}

    def fetch_weather(self, lat: float, lon: float) -> dict[str, Any]:
        ck = f"wx_{lat:.3f}_{lon:.3f}"
        cached = self._cache_read(ck)
        if cached:
            return {**cached, "cached": True}

        try:
            q = urllib.parse.urlencode({
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
                "current": "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
                "hourly": "precipitation_probability",
                "forecast_hours": "4",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
            })
            data = self._http_get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
            cur = data.get("current") or {}
            probs = (data.get("hourly") or {}).get("precipitation_probability") or []
            code = int(cur.get("weather_code") or 0)
            out = {
                "temp_f": round(float(cur.get("temperature_2m", 58.0)), 1),
                "precip_in": round(float(cur.get("precipitation", 0.0)), 2),
                "wind_mph": round(float(cur.get("wind_speed_10m", 8.0)), 1),
                "gusts_mph": round(float(cur.get("wind_gusts_10m", 14.0)), 1),
                "precip_prob_4h_pct": int(max(probs) if probs else 0),
                "condition": WMO_WEATHER_LABELS.get(code, "Fair"),
                "observed_at": cur.get("time") or "",
                "source": "open_meteo_live",
            }
            self._cache_write(ck, out)
            return out
        except Exception:
            return {
                "temp_f": None,
                "precip_in": 0.0,
                "wind_mph": None,
                "gusts_mph": None,
                "precip_prob_4h_pct": 0,
                "condition": "Live weather feed unreachable",
                "observed_at": "",
                "source": "weather_fallback",
            }

    def fetch_nyc_traffic(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        if not (_is_nyc_metro(float(orig["lat"]), float(orig["lon"])) or _is_nyc_metro(float(dest["lat"]), float(dest["lon"]))):
            return {"active": False, "corridors": [], "avg_mph": None, "source": "outside_nyc"}

        ck = "nycdot_speeds_latest"
        cached = self._cache_read(ck)
        if cached:
            return {**cached, "cached": True}

        try:
            rows = self._http_get_json(
                "https://data.cityofnewyork.us/resource/i4gi-tjb9.json?$order=:id%20DESC&$limit=45"
            )
            if isinstance(rows, list) and rows:
                corridors: list[dict[str, Any]] = []
                seen: set[str] = set()
                speeds: list[float] = []
                as_of = ""
                for r in rows:
                    name = (r.get("link_name") or "").strip()
                    spd_raw = r.get("speed")
                    if not name or spd_raw is None or name in seen:
                        continue
                    spd = float(spd_raw)
                    if spd <= 0 or spd > 80:
                        continue
                    seen.add(name)
                    speeds.append(spd)
                    if not as_of and r.get("data_as_of"):
                        as_of = str(r["data_as_of"])
                    if len(corridors) < 5:
                        corridors.append({
                            "corridor": name,
                            "speed_mph": round(spd, 1),
                            "borough": r.get("borough") or "NYC",
                        })
                avg_mph = round(sum(speeds) / len(speeds), 1) if speeds else None
                out = {
                    "active": bool(corridors),
                    "corridors": corridors,
                    "avg_mph": avg_mph,
                    "as_of": as_of,
                    "source": "nyc_dot_live",
                }
                self._cache_write(ck, out)
                return out
        except Exception:
            pass

        return {"active": False, "corridors": [], "avg_mph": None, "source": "nyc_dot_unavailable"}


def _summarize_fleet(plan: dict[str, Any] | None, truck_id_override: str | None = None) -> dict[str, Any]:
    trucks_in_plan = (plan or {}).get("trucks") or []
    chosen_tid = truck_id_override or (trucks_in_plan[0].get("truck_id") if trucks_in_plan else "uhaul_26") or "uhaul_26"
    spec = catalog.get_truck(chosen_tid) or catalog.get_truck("uhaul_26") or {}

    max_ext_h = float(spec.get("ext_height_in") or 144.0)
    max_ext_l = float(spec.get("ext_length_in") or 404.0)
    gvwr = int(spec.get("gvwr_lb") or 25999)
    dual_rear = bool(spec.get("dual_rear_wheel", True))
    truck_names: list[str] = []

    total_items = 0
    total_boxes = 0
    fragile_count = 0
    heavy_count = 0
    cargo_weight_lb = 0.0

    for t in trucks_in_plan:
        tspec = catalog.get_truck(t.get("truck_id") or chosen_tid) or spec
        max_ext_h = max(max_ext_h, float(tspec.get("ext_height_in") or max_ext_h))
        max_ext_l = max(max_ext_l, float(tspec.get("ext_length_in") or max_ext_l))
        gvwr = max(gvwr, int(tspec.get("gvwr_lb") or gvwr))
        dual_rear = dual_rear or bool(tspec.get("dual_rear_wheel", False))
        truck_names.append(tspec.get("name") or chosen_tid)
        for it in t.get("items") or []:
            total_items += 1
            if it.get("is_box"):
                total_boxes += 1
            if it.get("fragile"):
                fragile_count += 1
            if it.get("two_person") or float(it.get("weight_lb") or 0) > 50.0:
                heavy_count += 1
            cargo_weight_lb += float(it.get("weight_lb") or 0.0)

    truck_count = max(1, len(trucks_in_plan))
    safe_buffer_in = max_ext_h + 6.0  # +6 in buffer for road crown, snow/asphalt repaving, and bounce
    curb_slot_ft = int(math.ceil((max_ext_l / 12.0) + 12.0))  # bumper-to-bumper + 12 ft pull-out loading ramp

    return {
        "truck_id": chosen_tid,
        "truck_name": spec.get("name") or "U-Haul 26 ft",
        "truck_count": truck_count,
        "fleet_label": f"{truck_count} × {spec.get('name') or 'U-Haul 26 ft'}" if truck_count > 1 else (spec.get("name") or "U-Haul 26 ft"),
        "ext_height_in": max_ext_h,
        "ext_height_label": fmt_inches_ft(max_ext_h),
        "recommended_nav_height_label": fmt_inches_ft(safe_buffer_in),
        "recommended_nav_height_in": safe_buffer_in,
        "ext_length_ft": round(max_ext_l / 12.0, 1),
        "curb_space_needed_ft": curb_slot_ft,
        "gvwr_lb": gvwr,
        "axles": int(spec.get("axles") or 2),
        "dual_rear_wheel": dual_rear,
        "toll_class": "2-Axle, 6-Tire Single-Unit Commercial Truck" if dual_rear else "2-Axle, 4-Tire Light Box Truck",
        "total_pieces": total_items,
        "total_boxes": total_boxes,
        "fragile_pieces": fragile_count,
        "two_person_pieces": heavy_count,
        "cargo_weight_lb": round(cargo_weight_lb, 0),
    }


def _analyze_no_truck_roads(
    orig: dict[str, Any],
    dest: dict[str, Any],
    osrm: dict[str, Any],
    overpass: dict[str, Any],
    fleet: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()

    primary_roads = [r.lower() for r in osrm.get("roads_on_primary") or []]
    alt_roads = [r.lower() for r in osrm.get("roads_on_alternatives") or []]
    all_route_text = " | ".join(primary_roads + alt_roads)

    # 1. Check live OSRM steps against known no-truck traps
    for item in KNOWN_NO_TRUCK_CORRIDORS:
        on_primary = any(any(p in r for p in item["patterns"]) for r in primary_roads)
        on_alt = any(any(p in r for p in item["patterns"]) for r in alt_roads)
        if on_primary or on_alt:
            seen.add(item["road"])
            warnings.append({
                "road": item["road"],
                "severity": "critical" if on_primary else "watch",
                "detected_on": "Consumer GPS fastest route!" if on_primary else "Nearby alternate route",
                "reason": item["rule"],
                "safe_alternative": item["safe_alt"],
            })

    # 2. Check live Overpass `maxheight` tags against truck exterior height + 6" safety margin
    req_in = float(fleet["recommended_nav_height_in"])
    for lc in overpass.get("low_clearances") or []:
        if float(lc["clearance_in"]) < req_in:
            rd = f"{lc['name']} ({lc['clearance_label']} posted clearance)"
            if rd not in seen:
                seen.add(rd)
                warnings.append({
                    "road": rd,
                    "severity": "critical" if float(lc["clearance_in"]) <= float(fleet["ext_height_in"]) else "watch",
                    "detected_on": "Live OpenStreetMap clearance tag along corridor",
                    "reason": (
                        f"Posted clearance is {lc['clearance_label']} vs your {fleet['truck_name']} "
                        f"roof height of {fleet['ext_height_label']} (need {fleet['recommended_nav_height_label']} w/ bounce buffer)."
                    ),
                    "safe_alternative": "Stay on designated Local Truck Routes and avoid railroad/parkway underpasses.",
                })

    # 3. Check live Overpass `hgv=no` bans
    for hgv_rd in overpass.get("hgv_bans") or []:
        if hgv_rd not in seen:
            seen.add(hgv_rd)
            warnings.append({
                "road": hgv_rd,
                "severity": "watch",
                "detected_on": "Live OSM truck restriction (`hgv=no`)",
                "reason": "Signed 'No Commercial Vehicles / No Trucks' in corridor.",
                "safe_alternative": "Use parallel signed Truck Route avenues.",
            })

    # 4. If in NYC metro, ensure core NYC Parkway & Local Truck Route guidance is surfaced even on short avenue hops
    in_nyc = _is_nyc_metro(float(orig["lat"]), float(orig["lon"])) or _is_nyc_metro(float(dest["lat"]), float(dest["lon"]))
    if in_nyc and not any("FDR" in w["road"] or "Parkway" in w["road"] for w in warnings):
        warnings.append({
            "road": "All NYC Parkways (FDR Drive, Henry Hudson Pkwy N of 59th, Belt Pkwy) & Brooklyn Bridge",
            "severity": "watch",
            "detected_on": "NYC Commercial Vehicle Rule",
            "reason": (
                f"NY law classifies every rental box truck ({fleet['fleet_label']}, {fleet['ext_height_label']} tall) "
                "as a commercial vehicle—banned on all Parkways and the Brooklyn Bridge."
            ),
            "safe_alternative": (
                "Stick to NYC DOT Local Truck Routes (Canal St, Houston St, 14th, 23rd, 34th St, "
                "and 6th/8th/9th/10th/11th/12th Aves); turn onto non-truck cross streets only for your origin/destination block."
            ),
        })

    if not warnings and not in_nyc and not all_route_text:
        warnings.append({
            "road": "Parkways, Historic Bridges & Low Underpasses (< " + fleet["recommended_nav_height_label"] + ")",
            "severity": "watch",
            "detected_on": "Truck Clearance Rule",
            "reason": f"Your {fleet['truck_name']} needs {fleet['recommended_nav_height_label']} vertical clearance.",
            "safe_alternative": "Avoid any road named 'Parkway' and watch yellow diamond clearance signs at rail bridges.",
        })

    return warnings[:5]


def _analyze_tolls(
    orig: dict[str, Any],
    dest: dict[str, Any],
    osrm: dict[str, Any],
    overpass: dict[str, Any],
    fleet: dict[str, Any],
) -> dict[str, Any]:
    roads_blob = " | ".join((osrm.get("roads_on_primary") or []) + (overpass.get("toll_points") or [])).lower()
    dual = bool(fleet["dual_rear_wheel"])
    items: list[dict[str, Any]] = []

    orig_state = (orig.get("state") or "").upper()
    dest_state = (dest.get("state") or "").upper()
    orig_crz = _is_manhattan_crz(float(orig["lat"]), float(orig["lon"]))
    dest_crz = _is_manhattan_crz(float(dest["lat"]), float(dest["lon"]))
    in_nyc = _is_nyc_metro(float(orig["lat"]), float(orig["lon"])) or _is_nyc_metro(float(dest["lat"]), float(dest["lon"]))

    # Port Authority Hudson River crossings (NJ -> NY eastbound tolled)
    if any(k in roads_blob for k in ("lincoln tunnel", "holland tunnel", "george washington", "i-95", "nj-495")) or (
        orig_state in ("NJ", "NEW JERSEY") and in_nyc
    ):
        items.append({
            "name": "Hudson River Crossing (Lincoln Tunnel / GW Bridge — Eastbound into NY)",
            "estimate": "$32–$46 E-ZPass (commercial 2-axle/6-tire) · ~$16–$22 light 4-tire" if dual else "$16–$22 E-ZPass",
            "note": "Tolled entering NY only (westbound NY→NJ is $0). Dual-rear-wheel U-Hauls (15/20/26 ft) bill at the 2-axle commercial truck rate.",
        })

    # MTA Tunnels / Bridges
    if any(k in roads_blob for k in ("queens-midtown", "queens midtown", "midtown tunnel", "hugh l. carey", "battery tunnel", "rfk", "triborough", "verrazzano", "whitestone", "throgs neck")):
        items.append({
            "name": "MTA Cashless Bridge / Tunnel Gantry",
            "estimate": "$21–$34 E-ZPass (commercial box truck) · higher by mail" if dual else "$7–$11 E-ZPass",
            "note": "Free East River truck alternatives: Manhattan Bridge (lower roadway), Williamsburg Bridge (outer roadways), or Queensboro lower outer lanes—NOT Brooklyn Bridge.",
        })

    # Manhattan Congestion Relief Zone (south of 60th St)
    if dest_crz and not orig_crz:
        items.append({
            "name": "Manhattan Congestion Relief Zone (Entering South of 60th St)",
            "estimate": "~$21.60 peak / $5.40 overnight (Single-Unit Truck E-ZPass)" if dual else "~$9.00–$14.40 peak E-ZPass",
            "note": "Charged once when entering Manhattan at or below 60th St (tunnel crossing credits apply if entering via Lincoln/Holland/QMT).",
        })
    elif orig_crz and dest_crz and not items:
        items.append({
            "name": "Surface Avenue Move Inside Lower/Midtown Manhattan",
            "estimate": "$0 Bridge/Tunnel Tolls on Local Avenues",
            "note": "Staying on Manhattan avenues between Point A and Point B avoids river-crossing tolls; avoid exiting onto excluded perimeter highways and re-entering.",
        })

    # Generic live OSM toll detection outside NYC
    for tp in overpass.get("toll_points") or []:
        if not any(tp.lower() in it["name"].lower() for it in items):
            items.append({
                "name": f"Tolled Segment: {tp}",
                "estimate": "Commercial 2-axle rate applies" if dual else "Standard 2-axle rate",
                "note": "Detected live via OpenStreetMap `toll=yes` along your route corridor.",
            })

    if not items:
        items.append({
            "name": "Primary Corridor Toll Check",
            "estimate": "$0 tolled crossings detected on primary street route",
            "note": (
                "If you detour onto a turnpike or tolled bridge/tunnel, remember 15–26 ft U-Hauls have dual rear wheels (6 tires) "
                "and bill as Single-Unit Commercial Trucks."
            ),
        })

    plate_tip = (
        "Rental Truck E-ZPass Tip: Rental boxes use overhead plate billing that tacks on a $15–$25/day processor fee. "
        "Bring your own portable E-ZPass on the windshield (check dual-wheel rules) or budget for Toll-by-Plate."
    )
    return {
        "has_tolls": any("$0" not in it["estimate"] for it in items),
        "toll_class": fleet["toll_class"],
        "items": items[:4],
        "rental_plate_tip": plate_tip,
    }


def _build_city_parking_tips(
    orig: dict[str, Any],
    dest: dict[str, Any],
    fleet: dict[str, Any],
    dest_wx: dict[str, Any],
) -> dict[str, Any]:
    is_city = dest.get("urban_tier") == "dense_city" or orig.get("urban_tier") == "dense_city"
    curb_ft = fleet["curb_space_needed_ft"]
    dest_low = (dest.get("label") or "").lower()
    in_nyc = _is_nyc_metro(float(dest["lat"]), float(dest["lon"]))

    tips: list[str] = []
    if "penn" in dest_low or "31st" in dest_low or "moynihan" in dest_low:
        tips.append(
            f"Penn District Curb & Dock Rules: W 31st & W 33rd St (between 7th & 9th Ave) have strict 'Commercial Vehicles Only — Loading & Unloading' zones (max 3 hrs). Reserve roughly {curb_ft} ft so your {fleet['ext_length_ft']} ft truck + pull-out ramp fit cleanly."
        )
        tips.append(
            "Approach from 8th, 9th, or 10th Ave Local Truck Routes—never block the 8th Ave bus lane, protected bike lane, or crosswalks (instant camera/NYPD tow ticket)."
        )
        tips.append(
            f"Curb Roof Watch: Street-side scaffolding sheds, café awnings, and tree limbs sit 6–12 in lower at the curb tilt—spot your {fleet['ext_height_label']} box roof before pulling flush to the sidewalk."
        )
    elif in_nyc:
        tips.append(
            f"NYC Curb Rules: Reserve ~{curb_ft} ft of curb ({fleet['ext_length_ft']} ft truck + 12 ft ramp). Stay 15 ft clear of fire hydrants, out of bus/bike lanes, and check red 'No Standing Anytime' vs 'Commercial Loading Only' signs."
        )
        tips.append(
            "Keep one person with the open truck (or leave a phone number on the dash while actively carrying boxes) and check Alternate Side Street Cleaning hours."
        )
        tips.append(
            f"Watch NYC sidewalk scaffolding sheds and low tree limbs at the curb crown—your roof is {fleet['ext_height_label']} high."
        )
    elif is_city:
        tips.append(
            f"City Curb Footprint: You need ~{curb_ft} ft of straight curb ({fleet['ext_length_ft']} ft truck + pull-out ramp). Scout loading zones on your block before pulling in so you never have to reverse a box truck into city traffic."
        )
        tips.append(
            "Check meter/commercial loading placards, stay 15 ft off fire hydrants, keep hazard flashers + orange cones out by the ramp, and confirm freight elevator hours ahead of arrival."
        )
        tips.append(
            f"Curbside Overhead Check: Low street trees, balconies, and storefront awnings overhang the curb—spot your {fleet['ext_height_label']} box corner when parking."
        )
    else:
        tips.append(
            f"Arrival Staging: Plan ~{curb_ft} ft of level space for the {fleet['truck_name']} + ramp. Walk the driveway first to check low utility wires, basketball hoops, and tree branches below {fleet['recommended_nav_height_label']}."
        )
        tips.append(
            "Back in with a spotter standing visible in your driver-side mirror, chock the rear wheels on any incline, and stage Stop 1 boxes closest to the front door."
        )

    if (dest_wx.get("precip_in") or 0) > 0 or (dest_wx.get("precip_prob_4h_pct") or 0) >= 40:
        tips.append(
            "Live Rain Alert at Destination: Lay a moving blanket at the base of the metal ramp (wet ramps get slick fast) and stage boxes inside the lobby/vestibule instead of on the sidewalk."
        )

    return {
        "is_city": is_city,
        "context_badge": "Dense City Curb & Dock Mode" if is_city else "Driveway & Local Street Mode",
        "curb_space_needed_ft": curb_ft,
        "tips": tips,
    }


def _build_phone_links(orig_str: str, dest_str: str, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, str]:
    o_enc = urllib.parse.quote(orig_str)
    d_enc = urllib.parse.quote(dest_str)
    return {
        "google_maps": f"https://www.google.com/maps/dir/?api=1&origin={o_enc}&destination={d_enc}&travelmode=driving",
        "google_maps_no_tolls": f"https://www.google.com/maps/dir/?api=1&origin={o_enc}&destination={d_enc}&travelmode=driving&avoid=tolls",
        "apple_maps": f"https://maps.apple.com/?saddr={o_enc}&daddr={d_enc}&dirflg=d",
        "waze": f"https://waze.com/ul?ll={dest['lat']:.5f},{dest['lon']:.5f}&navigate=yes",
        "trucker_path_web": "https://truckerpath.com/trucker-path-app/",
        "hammer_web": "https://www.hammer.app/",
    }


def _default_stage_nudges(fleet: dict[str, Any], parking: dict[str, Any], wx_dest: dict[str, Any]) -> dict[str, str]:
    rain_bit = (
        " Rain is in the live forecast—keep stretch wrap handy for upholstered pieces."
        if ((wx_dest.get("precip_in") or 0) > 0 or (wx_dest.get("precip_prob_4h_pct") or 0) >= 40)
        else ""
    )
    return {
        "pack": (
            f"Pack one small 'Open-First' tote (chargers, box cutter, furniture bolts, water, paper towels) "
            f"so you don't have to hunt through {max(1, fleet['total_boxes'])} boxes tonight.{rain_bit}"
        ),
        "load": (
            f"Follow the 3D Load scrubber from cab wall to rear door: heavy two-person pieces ({fleet['two_person_pieces']}) "
            f"anchor the floor, fragile items ({fleet['fragile_pieces']}) ride top-only, ratchet-strap each tier."
        ),
        "drive": (
            f"Before shifting into Drive: set Commercial Truck Mode ({fleet['recommended_nav_height_label']} height) on your phone, "
            f"adjust wide tow mirrors, and skip every Parkway."
        ),
        "park_unload": (
            f"Claim ~{parking['curb_space_needed_ft']} ft at the curb/dock, spot the {fleet['ext_height_label']} roof against awnings/trees, "
            f"and switch the 3D view to 'Unload (LIFO)' so Stop 1 comes straight off the tail."
        ),
        "unpack": (
            "No rush to finish everything at once—open your Essentials bag first, assemble beds/seating, "
            "and check off rooms below at your own pace down to the very last item."
        ),
    }


def build_route_brief(
    origin: str | None = None,
    destination: str | None = None,
    plan: dict[str, Any] | None = None,
    truck_id: str | None = None,
    nav_app: str = "google_maps",
    run_dir: Path | None = None,
    client: LiveRouteDataClient | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Pull real-time geo/route/weather/traffic data and build a calm, complete Point A->B brief."""
    t0 = time.time()
    live = client or LiveRouteDataClient()
    orig_q = (origin or "").strip() or DEFAULT_ORIGIN
    dest_q = (destination or "").strip() or DEFAULT_DESTINATION
    nav_key = nav_app if nav_app in NAV_APP_PROFILES else "google_maps"

    fleet = _summarize_fleet(plan, truck_id_override=truck_id)

    # Step 1: Geocode Point A & Point B in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_orig = pool.submit(live.geocode, orig_q)
        f_dest = pool.submit(live.geocode, dest_q)
        orig_geo = f_orig.result()
        dest_geo = f_dest.result()

    # Step 2: Pull live OSRM street route, Overpass clearances/bans, Weather at A & B, and NYC DOT traffic in parallel!
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_osrm = pool.submit(live.fetch_osrm_route, orig_geo, dest_geo)
        f_ovp = pool.submit(live.fetch_overpass_restrictions, orig_geo, dest_geo)
        f_wxa = pool.submit(live.fetch_weather, float(orig_geo["lat"]), float(orig_geo["lon"]))
        f_wxb = pool.submit(live.fetch_weather, float(dest_geo["lat"]), float(dest_geo["lon"]))
        f_tfc = pool.submit(live.fetch_nyc_traffic, orig_geo, dest_geo)

        osrm = f_osrm.result()
        overpass = f_ovp.result()
        wx_orig = f_wxa.result()
        wx_dest = f_wxb.result()
        traffic = f_tfc.result()

    # Compute realistic commercial box-truck drive time (slower acceleration + local truck avenues + live traffic speed)
    base_min = int(osrm.get("car_duration_min") or 15)
    truck_factor = 1.28 if (orig_geo.get("urban_tier") == "dense_city" or dest_geo.get("urban_tier") == "dense_city") else 1.15
    if traffic.get("avg_mph") is not None and float(traffic["avg_mph"]) < 16.0:
        truck_factor += 0.18
    truck_eta_min = max(6, int(round(base_min * truck_factor)))

    no_truck_warnings = _analyze_no_truck_roads(orig_geo, dest_geo, osrm, overpass, fleet)
    tolls = _analyze_tolls(orig_geo, dest_geo, osrm, overpass, fleet)
    parking = _build_city_parking_tips(orig_geo, dest_geo, fleet, wx_dest)
    nav_profile = dict(NAV_APP_PROFILES[nav_key])
    phone_links = _build_phone_links(orig_q, dest_q, orig_geo, dest_geo)
    stage_nudges = _default_stage_nudges(fleet, parking, wx_dest)

    # Weather/wind alert banner (only if actionable — never noisy!)
    max_gust = max(float(wx_orig.get("gusts_mph") or 0), float(wx_dest.get("gusts_mph") or 0))
    weather_note = None
    if max_gust >= 25.0:
        weather_note = (
            f"Live Crosswind Heads-Up ({max_gust:.0f} mph gusts): Take bridges and open highway stretches slower "
            f"in your high-wall {fleet['ext_height_label']} {fleet['truck_name']}."
        )
    elif (wx_dest.get("precip_in") or 0) > 0 or (wx_orig.get("precip_in") or 0) > 0:
        weather_note = "Active precipitation right now—keep furniture pads dry inside the truck until items cross the threshold."

    # Step 3: Gemini Decisions API (`gemini-decision-1`) + Gemini 4 (`gemini-4-neon`) calm synthesis
    decision_meta: dict[str, Any] = {
        "choice": "reroute_parkways_and_low_bridges" if any(w["severity"] == "critical" for w in no_truck_warnings) else "commercial_truck_avenues_and_curb_plan",
        "confidence": None,
        "via": "deterministic_rules",
    }
    ai_synthesis: dict[str, Any] | None = None

    if use_llm:
        _load_env()
    if use_llm and os.environ.get("GEMINI_API_KEY"):
        telemetry_summary = {
            "origin": orig_geo.get("label"),
            "destination": dest_geo.get("label"),
            "distance_miles": osrm.get("distance_miles"),
            "truck_eta_min": truck_eta_min,
            "fleet": {
                "label": fleet["fleet_label"],
                "ext_height": fleet["ext_height_label"],
                "nav_buffer_height": fleet["recommended_nav_height_label"],
                "curb_space_ft": fleet["curb_space_needed_ft"],
                "toll_class": fleet["toll_class"],
            },
            "selected_nav_app": nav_profile["name"],
            "nav_app_has_truck_mode": nav_profile["has_native_truck_mode"],
            "osrm_car_roads": osrm.get("roads_on_primary", [])[:12],
            "detected_no_truck_warnings": no_truck_warnings,
            "tolls": tolls["items"],
            "live_weather_origin": wx_orig,
            "live_weather_dest": wx_dest,
            "live_nyc_traffic": traffic,
            "destination_is_city": parking["is_city"],
        }
        try:
            dec_q = (
                "Given this live moving-truck route telemetry:\n"
                + json.dumps(telemetry_summary, ensure_ascii=False)
                + "\nWhat is the primary driver advisory level needed for this Point A to Point B move?"
            )
            dec = for_job("decide", run_dir).decide(
                dec_q,
                options=[
                    "reroute_off_parkways_or_low_bridges",
                    "commercial_truck_avenues_and_city_curb_plan",
                    "straightforward_local_truck_drive",
                ],
                criteria={
                    "reroute_off_parkways_or_low_bridges": "Passenger-car GPS touches a truck-banned parkway, restricted bridge/tunnel, or low clearance below the truck height + 6 in buffer.",
                    "commercial_truck_avenues_and_city_curb_plan": "Dense city move requiring designated truck avenues, commercial curb/loading-zone awareness, and truck-mode GPS check.",
                    "straightforward_local_truck_drive": "Clear suburban/highway truck route with no low clearances or restricted parkways.",
                },
                label="route_advisory_level",
            )
            decision_meta = {
                "choice": dec.get("answer"),
                "confidence": round(float(dec.get("confidence") or 0.0), 3),
                "via": dec.get("via", "decisions_api"),
            }
        except LLMError:
            pass

        try:
            prompt = (
                "You are Pack It Up's calm, supportive move-day co-pilot. A user is moving from Point A to Point B "
                "using the solved rental truck fleet below, informed by LIVE real-time routing, weather, clearance, and traffic data.\n\n"
                f"LIVE TELEMETRY JSON:\n{json.dumps(telemetry_summary, indent=2, ensure_ascii=False)}\n\n"
                "Write concise, reassuring, street-smart tips (never alarmist, never preachy or overbearing—like a calm friend who has driven "
                "moving trucks in the city 100 times). Cover:\n"
                "1. `calm_headline`: <= 14 words summarizing the drive & truck clearance calmly.\n"
                "2. `route_summary`: 1-2 short sentences citing real-time conditions (distance, truck ETA, live weather/traffic speeds if present).\n"
                "3. `toll_tips`: 2-3 crisp bullets on exact tolls/CRZ/E-ZPass vs rental plate fees for this route & axle class.\n"
                "4. `no_truck_tips`: 2-3 crisp bullets naming specific roads/parkways/bridges to avoid for this Point A->B corridor and safe truck alternatives.\n"
                "5. `nav_mode_tip`: 1-2 crisp sentences reminding them to switch to Commercial Truck Mode on their phone (explicitly noting whether their chosen app has a real truck mode or needs Hammer/Trucker Path + exact height buffer).\n"
                "6. `city_parking_tips`: 2-3 practical parking/curb/unloading bullets tailored to Point B (city loading zones/hydrants/scaffolding/curb length if urban, driveway/wires if suburban).\n"
                "7. `gentle_stage_nudges`: one short, supportive 1-sentence nudge for each stage (`pack`, `load`, `drive`, `park_unload`, `unpack`) that carries them calmly through unpacking their very last item."
            )
            ai_synthesis = for_job("route", run_dir).generate_json(
                prompt,
                schema=ROUTE_SYNTHESIS_SCHEMA,
                prompt_version="route_brief_v1",
                label="route_brief",
            )
            if isinstance(ai_synthesis.get("gentle_stage_nudges"), dict):
                stage_nudges = {**stage_nudges, **ai_synthesis["gentle_stage_nudges"]}
        except LLMError:
            ai_synthesis = None

    live_sources_used = [
        s for s in [
            "OpenStreetMap Nominatim" if orig_geo.get("source") == "nominatim_live" or dest_geo.get("source") == "nominatim_live" else None,
            "OSRM Live Street Router" if osrm.get("source") == "osrm_live" else None,
            "OSM Overpass Clearances & HGV" if overpass.get("source") == "overpass_live" else None,
            "Open-Meteo Live Weather & Wind" if wx_dest.get("source") == "open_meteo_live" else None,
            "NYC DOT Real-Time Traffic Detectors" if traffic.get("source") == "nyc_dot_live" else None,
            "Gemini 4 Neon + Decisions API" if ai_synthesis else None,
        ] if s
    ]

    calm_headline = (
        (ai_synthesis or {}).get("calm_headline")
        or f"{osrm['distance_miles']} mi · ~{truck_eta_min} min truck drive · keep {fleet['recommended_nav_height_label']} clearance"
    )
    wx_snippet = (
        f" Live at destination: {wx_dest['temp_f']:.0f}°F, {wx_dest['condition'].lower()} (gusts {wx_dest['gusts_mph']:.0f} mph)."
        if wx_dest.get("temp_f") is not None and wx_dest.get("gusts_mph") is not None
        else ""
    )
    tfc_snippet = (
        f" NYC DOT live sensors average {traffic['avg_mph']} mph across nearby corridors."
        if traffic.get("avg_mph") is not None
        else ""
    )
    route_summary = (
        (ai_synthesis or {}).get("route_summary")
        or f"From {orig_geo['short_label']} to {dest_geo['short_label']} ({osrm['distance_miles']} mi, ~{truck_eta_min} min in a {fleet['fleet_label']}).{wx_snippet}{tfc_snippet}"
    )

    return {
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "latency_ms": int(round((time.time() - t0) * 1000)),
        "live_sources": live_sources_used or ["Built-in Truck Corridor Rules"],
        "origin": orig_geo,
        "destination": dest_geo,
        "fleet": fleet,
        "drive": {
            "distance_miles": osrm["distance_miles"],
            "car_duration_min": osrm["car_duration_min"],
            "truck_eta_min": truck_eta_min,
            "roads_on_car_route": osrm.get("roads_on_primary") or [],
            "calm_headline": calm_headline,
            "route_summary": route_summary,
            "weather_alert": weather_note,
        },
        "weather": {
            "origin": wx_orig,
            "destination": wx_dest,
        },
        "traffic": traffic,
        "decision": decision_meta,
        "nav_reminder": {
            "selected_app": nav_profile,
            "available_apps": [
                {"id": k, "name": v["name"], "has_native_truck_mode": v["has_native_truck_mode"], "badge": v["badge"]}
                for k, v in NAV_APP_PROFILES.items()
            ],
            "truck_profile_card": (
                f"Height: {fleet['recommended_nav_height_label']} ({fleet['ext_height_label']} actual + 6\" buffer) · "
                f"Length: {fleet['ext_length_ft']} ft · GVWR: {fleet['gvwr_lb']:,} lb · {fleet['toll_class']}"
            ),
            "tip": (ai_synthesis or {}).get("nav_mode_tip") or nav_profile["how_to_enable"],
            "links": phone_links,
        },
        "no_truck_roads": {
            "warnings": no_truck_warnings,
            "overpass_low_clearances": overpass.get("low_clearances") or [],
            "ai_bullets": (ai_synthesis or {}).get("no_truck_tips") or [],
        },
        "tolls": {
            **tolls,
            "ai_bullets": (ai_synthesis or {}).get("toll_tips") or [],
        },
        "parking": {
            **parking,
            "ai_bullets": (ai_synthesis or {}).get("city_parking_tips") or [],
        },
        "stage_nudges": stage_nudges,
    }
