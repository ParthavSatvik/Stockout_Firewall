"""Distance/time estimation used as a planning input to the optimizer and as the
fallback when no routing provider is configured.

This is a straight-line (haversine) estimate scaled by a road-circuity factor, NOT a
real road route. Callers must label it as an estimate. When GOOGLE_MAPS_API_KEY is
configured, app.providers.routes refines the chosen allocations' route_distance_km /
route_duration_minutes / route_source after the optimizer has picked suppliers.
"""
import math

EARTH_RADIUS_KM = 6371.0
ROAD_CIRCUITY_FACTOR = 1.35  # roads are never a straight line; a common rule-of-thumb multiplier
AVG_URBAN_SPEED_KMPH = 22.0
HANDLING_HOURS = 1.5  # loading/dispatch overhead before a vehicle departs
DELIVERY_BASE_FEE_INR = 60.0
DELIVERY_PER_KM_INR = 12.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if (lat1, lon1) == (0.0, 0.0) or (lat2, lon2) == (0.0, 0.0):
        return 5.0  # unknown coordinates: assume a modest in-city default rather than 0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return round(haversine_km(lat1, lon1, lat2, lon2) * ROAD_CIRCUITY_FACTOR, 2)


def estimate_duration_minutes(distance_km: float) -> float:
    return round((distance_km / AVG_URBAN_SPEED_KMPH) * 60 + HANDLING_HOURS * 60, 1)


def estimate_delivery_cost_inr(distance_km: float) -> float:
    return round(DELIVERY_BASE_FEE_INR + DELIVERY_PER_KM_INR * distance_km, 2)
