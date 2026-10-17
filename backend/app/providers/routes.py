"""Route/distance provider abstraction.

`EstimatedRouteProvider` is the default: a haversine straight-line distance scaled by
a road-circuity factor (see app.services.geo), always labelled `source="estimated"`.

`GoogleRoutesProvider` calls Routes API v2 ComputeRouteMatrix when GOOGLE_MAPS_API_KEY
is configured. Exact REST paths/headers were confirmed from the public API reference;
pricing/quota were not verified in this session (see docs/PROVIDER_NOTES.md). On any
HTTP error it falls back to the estimate rather than failing the request.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.services.geo import estimate_delivery_cost_inr, estimate_distance_km, estimate_duration_minutes

settings = get_settings()

ROUTES_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


@dataclass
class RouteEstimate:
    distance_km: float
    duration_minutes: float
    cost_inr: float
    source: str  # "estimated" | "google_routes"


class RouteProvider(ABC):
    @abstractmethod
    def estimate(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate: ...


class EstimatedRouteProvider(RouteProvider):
    def estimate(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        distance_km = estimate_distance_km(origin[0], origin[1], destination[0], destination[1])
        return RouteEstimate(
            distance_km=distance_km,
            duration_minutes=estimate_duration_minutes(distance_km),
            cost_inr=estimate_delivery_cost_inr(distance_km),
            source="estimated",
        )


class GoogleRoutesProvider(RouteProvider):
    def __init__(self) -> None:
        if not settings.google_maps_configured:
            raise RuntimeError("GoogleRoutesProvider requires GOOGLE_MAPS_API_KEY")
        self._fallback = EstimatedRouteProvider()

    def estimate(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        headers = {
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": "originIndex,destinationIndex,status,condition,distanceMeters,duration",
            "Content-Type": "application/json",
        }
        body = {
            "origins": [{"waypoint": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}}],
            "destinations": [
                {"waypoint": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}}}
            ],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }
        try:
            resp = httpx.post(ROUTES_MATRIX_URL, json=body, headers=headers, timeout=10.0)
            resp.raise_for_status()
            rows = resp.json()
            element = rows[0] if rows else {}
            if element.get("status") not in (None, "OK"):
                return self._fallback.estimate(origin, destination)
            distance_km = round(element["distanceMeters"] / 1000.0, 2)
            duration_seconds = int(str(element["duration"]).rstrip("s"))
            duration_minutes = round(duration_seconds / 60.0, 1)
            return RouteEstimate(
                distance_km=distance_km,
                duration_minutes=duration_minutes,
                cost_inr=estimate_delivery_cost_inr(distance_km),
                source="google_routes",
            )
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return self._fallback.estimate(origin, destination)


def get_route_provider() -> RouteProvider:
    if settings.google_maps_configured:
        return GoogleRoutesProvider()
    return EstimatedRouteProvider()
