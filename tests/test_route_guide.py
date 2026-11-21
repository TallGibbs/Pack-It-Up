"""Tests for Track B Real-Time Point A->B Truck Route Guide, City Parking & Stage Support."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from backend import catalog, route_guide, solver
from backend.app import app


class FakeLiveRouteClient(route_guide.LiveRouteDataClient):
    """Deterministic fake live telemetry client simulating real-time OSRM, Overpass, Open-Meteo & NYC DOT."""

    def __init__(self):
        super().__init__(use_cache=False)

    def geocode(self, address: str) -> dict[str, Any]:
        low = address.lower()
        if "hoboken" in low or "nj" in low:
            return {
                "query": address,
                "label": "Hoboken, Washington St, NJ 07030",
                "short_label": "Hoboken, NJ",
                "lat": 40.7433,
                "lon": -74.0324,
                "city": "Hoboken",
                "borough": "",
                "state": "NJ",
                "postal_code": "07030",
                "urban_tier": "dense_city",
                "source": "nominatim_live",
            }
        if "penn" in low or "31st" in low:
            return {
                "query": address,
                "label": "NY Penn Station, 234 W 31st St, New York, NY 10001",
                "short_label": "Midtown West, NY",
                "lat": 40.7506,
                "lon": -73.9935,
                "city": "New York",
                "borough": "Manhattan",
                "state": "NY",
                "postal_code": "10001",
                "urban_tier": "dense_city",
                "source": "nominatim_live",
            }
        return {
            "query": address,
            "label": "Williamsburg, Brooklyn, NY 11211",
            "short_label": "Brooklyn, NY",
            "lat": 40.7178,
            "lon": -73.9577,
            "city": "New York",
            "borough": "Brooklyn",
            "state": "NY",
            "postal_code": "11211",
            "urban_tier": "dense_city",
            "source": "nominatim_live",
        }

    def fetch_osrm_route(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        if orig.get("state") == "NJ":
            roads = ["Observer Hwy", "Holland Tunnel I-78", "Canal St", "8th Ave", "W 31st St"]
        else:
            roads = ["Bedford Ave", "Brooklyn Bridge", "FDR Drive", "E 34th St", "W 31st St"]
        return {
            "distance_miles": 4.9,
            "car_duration_min": 21,
            "roads_on_primary": roads,
            "roads_on_alternatives": ["Manhattan Bridge", "Henry Hudson Pkwy"],
            "sampled_coords": [[orig["lon"], orig["lat"]], [dest["lon"], dest["lat"]]],
            "source": "osrm_live",
        }

    def fetch_overpass_restrictions(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        return {
            "low_clearances": [
                {
                    "name": "Parkway Arch Underpass",
                    "raw_maxheight": "3.4 m",
                    "clearance_in": 133.9,
                    "clearance_label": "11' 2\"",
                }
            ],
            "hgv_bans": ["Park Ave Viaduct"],
            "toll_points": [],
            "source": "overpass_live",
        }

    def fetch_weather(self, lat: float, lon: float) -> dict[str, Any]:
        return {
            "temp_f": 51.0,
            "precip_in": 0.08,
            "wind_mph": 15.0,
            "gusts_mph": 28.0,
            "precip_prob_4h_pct": 75,
            "condition": "Light rain",
            "observed_at": "2026-11-21T13:15",
            "source": "open_meteo_live",
        }

    def fetch_nyc_traffic(self, orig: dict[str, Any], dest: dict[str, Any]) -> dict[str, Any]:
        return {
            "active": True,
            "corridors": [{"corridor": "Lincoln Tunnel E/B", "speed_mph": 12.4, "borough": "Manhattan"}],
            "avg_mph": 12.4,
            "as_of": "2026-11-21T13:14:00",
            "source": "nyc_dot_live",
        }


def test_truck_exterior_specs_and_height_parser():
    catalog.load_trucks.cache_clear()
    t26 = catalog.get_truck("uhaul_26")
    t10 = catalog.get_truck("uhaul_10")
    assert t26 is not None and t10 is not None
    assert t26["ext_height_in"] == 144.0
    assert t26["dual_rear_wheel"] is True
    assert t10["ext_height_in"] == 103.0
    assert t10["dual_rear_wheel"] is False

    assert route_guide.parse_height_to_inches("11'4\"") == 136.0
    assert route_guide.parse_height_to_inches("10 ft 6 in") == 126.0
    assert 137.0 <= (route_guide.parse_height_to_inches("3.5 m") or 0) <= 138.5
    assert route_guide.parse_height_to_inches("default") is None


def test_route_brief_catches_no_truck_traps_tolls_nav_and_city_parking():
    fake = FakeLiveRouteClient()
    brief = route_guide.build_route_brief(
        origin="Williamsburg, Brooklyn, NY 11211",
        destination="NY Penn Station, 234 W 31st St, New York, NY 10001",
        truck_id="uhaul_26",
        nav_app="google_maps",
        client=fake,
        use_llm=False,
    )

    # 1. Catches FDR Drive, Brooklyn Bridge & 11'2" low bridge against 12'0" U-Haul 26 ft
    warn_roads = " | ".join(w["road"] for w in brief["no_truck_roads"]["warnings"])
    assert "FDR Drive" in warn_roads
    assert "Brooklyn Bridge" in warn_roads
    assert "Parkway Arch Underpass" in warn_roads
    assert brief["fleet"]["ext_height_label"] == "12' 0\""
    assert brief["fleet"]["recommended_nav_height_label"] == "12' 6\""

    # 2. Phone nav app check: Google Maps flagged as lacking commercial truck mode; Hammer has it
    assert brief["nav_reminder"]["selected_app"]["has_native_truck_mode"] is False
    assert "NO commercial truck" in brief["nav_reminder"]["tip"]

    hammer_brief = route_guide.build_route_brief(
        origin="Hoboken, NJ",
        destination="NY Penn Station, 234 W 31st St, New York, NY 10001",
        truck_id="uhaul_26",
        nav_app="hammer",
        client=fake,
        use_llm=False,
    )
    assert hammer_brief["nav_reminder"]["selected_app"]["has_native_truck_mode"] is True
    assert hammer_brief["tolls"]["has_tolls"] is True
    assert "6-Tire" in hammer_brief["tolls"]["toll_class"]

    # 3. City parking + live weather/wind + supportive stage nudges through last item unpacked
    assert brief["parking"]["is_city"] is True
    assert brief["parking"]["curb_space_needed_ft"] >= 45
    assert any("Rain" in t or "ramp" in t for t in brief["parking"]["tips"])
    assert brief["drive"]["weather_alert"] is not None
    assert set(brief["stage_nudges"].keys()) == {"pack", "load", "drive", "park_unload", "unpack"}


def test_route_api_endpoints():
    client = TestClient(app)
    r_presets = client.get("/route/presets")
    assert r_presets.status_code == 200
    assert len(r_presets.json()["nav_apps"]) >= 5

    r_brief = client.post(
        "/route/brief",
        json={
            "run_id": "sample_venue",
            "origin": "The Malin SoHo, 387 Broadway, New York, NY 10013",
            "destination": "NY Penn Station, 234 W 31st St, New York, NY 10001",
            "nav_app": "waze",
            "use_llm": False,
        },
    )
    assert r_brief.status_code == 200
    body = r_brief.json()
    assert body["nav_reminder"]["selected_app"]["id"] == "waze"
    assert body["nav_reminder"]["selected_app"]["has_native_truck_mode"] is False
    assert body["parking"]["is_city"] is True
    assert len(body["no_truck_roads"]["warnings"]) >= 1
