"""
locator.py — Device location + nearby alcohol places via Nominatim (OpenStreetMap).
No API keys required.
"""

import math
import time
import requests

_NOM_HEADERS = {"User-Agent": "HUBERT-AlcoholGetter/1.0 (personal assistant)"}
_NOM_URL     = "https://nominatim.openstreetmap.org/search"

# Bounding-box half-width in degrees (≈ 16 km at mid-latitudes)
_BOX_DEG = 0.15


# ── Location ──────────────────────────────────────────────────────────────────

def get_location() -> dict:
    """Get approximate device location via IP geolocation (ip-api.com, free)."""
    r = requests.get("http://ip-api.com/json/", timeout=8)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"IP geolocation failed: {data.get('message', 'unknown error')}")
    return {
        "lat": data["lat"],
        "lng": data["lon"],
        "city": data.get("city", ""),
        "region": data.get("regionName", ""),
        "country": data.get("country", ""),
    }


# ── Distance ──────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _miles(km: float) -> float:
    return round(km * 0.621371, 1)


# ── Alcohol Type Inference ─────────────────────────────────────────────────────

_BEER_WORDS   = {"beer", "brew", "brewing", "brewery", "ale", "lager", "draft", "draught", "taproom", "tap room", "tavern"}
_WINE_WORDS   = {"wine", "winery", "vino", "cellar", "sommelier", "vineyard"}
_SPIRIT_WORDS = {"whiskey", "whisky", "bourbon", "rum", "tequila", "vodka", "gin", "spirits", "distillery", "cocktail", "speakeasy"}
_CIDER_WORDS  = {"cider"}
_MARGS_WORDS  = {"margarita", "cantina", "cerveceria", "tequila"}


def _infer_alcohol_types(amenity: str, shop: str, name: str) -> list[str]:
    nl = name.lower()

    # Bars / pubs / clubs
    if amenity in ("bar", "pub", "nightclub", "biergarten", "lounge"):
        types: list[str] = []
        if any(w in nl for w in _CIDER_WORDS):
            types.append("Cider")
        if any(w in nl for w in _MARGS_WORDS):
            types.append("Margaritas")
        if any(w in nl for w in _WINE_WORDS):
            types.append("Wine")
        if any(w in nl for w in _SPIRIT_WORDS):
            types.append("Whiskey & Spirits")
        if any(w in nl for w in _BEER_WORDS):
            types.append("Beer")
        if not types:
            types = ["Beer", "Cocktails", "Spirits"]
        return types

    # Dedicated bottle shops
    if shop in ("alcohol", "liquor", "spirits"):
        return ["Beer", "Wine", "Spirits", "Liquor — Full Selection"]
    if shop == "wine":
        return ["Wine", "Beer", "Spirits"]

    # Grocery / convenience
    if shop == "convenience":
        return ["Beer", "Wine (select)"]
    if shop in ("supermarket", "grocery"):
        return ["Beer", "Wine", "Spirits (select)"]

    # Gas stations — Texas allows off-premise beer + wine
    if amenity == "fuel":
        return ["Beer", "Wine (off-premise)"]

    # Breweries
    if any(w in nl for w in _BEER_WORDS):
        return ["Craft Beer", "Cider", "Brewery Exclusives"]

    return ["Beer", "Beverages"]


def _category_label(amenity: str, shop: str) -> str:
    if amenity == "bar":        return "Bar"
    if amenity == "pub":        return "Pub"
    if amenity == "nightclub":  return "Nightclub"
    if amenity == "biergarten": return "Beer Garden"
    if amenity == "lounge":     return "Lounge"
    if shop in ("alcohol", "liquor", "spirits"): return "Liquor Store"
    if shop == "wine":          return "Wine Shop"
    if shop == "supermarket":   return "Grocery Store"
    if shop == "convenience":   return "Convenience Store"
    if amenity == "fuel":       return "Gas Station"
    return "Store"


def _is_bar(amenity: str) -> bool:
    return amenity in ("bar", "pub", "nightclub", "biergarten", "lounge")


# ── Nominatim query ────────────────────────────────────────────────────────────

def _nom_search(amenity: str | None, shop: str | None, lat: float, lng: float) -> list[dict]:
    """Single Nominatim viewbox search. Returns raw result list."""
    params: dict = {
        "format":       "json",
        "limit":        50,
        "viewbox":      f"{lng - _BOX_DEG},{lat - _BOX_DEG},{lng + _BOX_DEG},{lat + _BOX_DEG}",
        "bounded":      1,
        "addressdetails": 1,
        "extratags":    1,
    }
    if amenity:
        params["amenity"] = amenity
    if shop:
        params["tag"] = f"shop={shop}"

    r = requests.get(_NOM_URL, params=params, headers=_NOM_HEADERS, timeout=15)
    r.raise_for_status()
    time.sleep(1.0)   # Nominatim ToS: max 1 req/s
    return r.json()


def _parse_result(el: dict, origin_lat: float, origin_lng: float) -> dict | None:
    name = el.get("display_name", "").split(",")[0].strip()
    if not name:
        return None

    el_lat = float(el.get("lat", 0))
    el_lng = float(el.get("lon", 0))
    if not el_lat or not el_lng:
        return None

    # Structured address
    addr_parts = el.get("address", {})
    street_num = addr_parts.get("house_number", "")
    road       = addr_parts.get("road", "")
    address    = f"{street_num} {road}".strip() or addr_parts.get("suburb", "See Google Maps")

    # OSM class/type for amenity / shop inference
    osm_type = el.get("type", "")
    osm_class = el.get("class", "")
    extra_tags = el.get("extratags", {}) or {}

    amenity = osm_type if osm_class == "amenity" else extra_tags.get("amenity", "")
    shop    = osm_type if osm_class == "shop"    else extra_tags.get("shop", "")

    dist_km = _haversine_km(origin_lat, origin_lng, el_lat, el_lng)
    dist_mi = _miles(dist_km)

    maps_url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&destination={el_lat},{el_lng}"
    )

    return {
        "name":          name,
        "address":       address,
        "distance_mi":   dist_mi,
        "distance_km":   dist_km,
        "maps_url":      maps_url,
        "alcohol_types": _infer_alcohol_types(amenity, shop, name),
        "category":      _category_label(amenity, shop),
        "is_bar":        _is_bar(amenity),
    }


# ── Main Public Function ───────────────────────────────────────────────────────

def query_nearby(lat: float, lng: float) -> tuple[list, list]:
    """
    Returns (bars, stores) sorted by distance.
      bars   — top 5 nearest (amenity=bar/pub/nightclub)
      stores — top 10 nearest (shops + gas stations)
    """
    seen_names: set[str] = set()
    bars:   list[dict] = []
    stores: list[dict] = []

    # Bar-type amenities — try both viewbox and city-name fallback
    for amenity in ("bar", "pub", "nightclub"):
        results = _nom_search(amenity, None, lat, lng)
        # If viewbox yields nothing, widen the search with a free-form city query
        if not results:
            try:
                r = requests.get(
                    _NOM_URL,
                    params={"amenity": amenity, "format": "json", "limit": 30,
                            "addressdetails": 1, "extratags": 1, "countrycodes": "us"},
                    headers=_NOM_HEADERS, timeout=15,
                )
                time.sleep(1.0)
                results = r.json()
                # Filter to those within ~25 km of origin
                results = [e for e in results if abs(float(e.get("lat", 0)) - lat) < 0.25
                           and abs(float(e.get("lon", 0)) - lng) < 0.25]
            except Exception:
                pass
        for el in results:
            place = _parse_result(el, lat, lng)
            if place and place["name"] not in seen_names:
                seen_names.add(place["name"])
                bars.append(place)

    # Store-type amenities
    for amenity in ("fuel",):
        for el in _nom_search(amenity, None, lat, lng):
            place = _parse_result(el, lat, lng)
            if place and place["name"] not in seen_names:
                seen_names.add(place["name"])
                stores.append(place)

    # Shops that sell alcohol
    for shop_tag in ("alcohol", "convenience", "supermarket"):
        params = {
            "format":       "json",
            "limit":        30,
            "viewbox":      f"{lng - _BOX_DEG},{lat - _BOX_DEG},{lng + _BOX_DEG},{lat + _BOX_DEG}",
            "bounded":      1,
            "addressdetails": 1,
            "extratags":    1,
            "q":            shop_tag,
        }
        # Manually use shop tag queries via free-form q parameter is unreliable;
        # use the class/type approach via amenity param with shop types
        try:
            r = requests.get(
                _NOM_URL,
                params={"amenity": shop_tag, "format": "json", "limit": 20,
                        "viewbox": f"{lng-_BOX_DEG},{lat-_BOX_DEG},{lng+_BOX_DEG},{lat+_BOX_DEG}",
                        "bounded": 1, "addressdetails": 1, "extratags": 1},
                headers=_NOM_HEADERS, timeout=15,
            )
            time.sleep(1.0)
            for el in r.json():
                place = _parse_result(el, lat, lng)
                if place and place["name"] not in seen_names:
                    seen_names.add(place["name"])
                    stores.append(place)
        except Exception:
            pass

    # Sort and trim
    bars   = sorted(bars,   key=lambda x: x["distance_km"])[:5]
    stores = sorted(stores, key=lambda x: x["distance_km"])[:10]

    return bars, stores
