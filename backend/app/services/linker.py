from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from shapely.geometry import LineString, Point


@dataclass(slots=True)
class VehicleObservation:
    route_id: str
    direction_id: int | None
    start_date: str | None
    start_time: str | None
    latitude: float
    longitude: float
    stop_id: str | None = None


@dataclass(slots=True)
class ScheduledTripCandidate:
    trip_id: str
    route_id: str
    direction_id: int | None
    start_date: str | None
    start_time: str | None
    shape_points: list[tuple[float, float]] | None = None
    next_stop_id: str | None = None


@dataclass(slots=True)
class MatchResult:
    trip_id: str | None
    score: float
    reason: str


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * radius * asin(sqrt(a))


def shape_distance_meters(observation: VehicleObservation, shape_points: list[tuple[float, float]]) -> float:
    if len(shape_points) < 2:
        return float("inf")
    line = LineString([(lon, lat) for lat, lon in shape_points])
    point = Point(observation.longitude, observation.latitude)
    projected = line.interpolate(line.project(point))
    return haversine_meters(
        observation.latitude,
        observation.longitude,
        projected.y,
        projected.x,
    )


def score_candidate(
    observation: VehicleObservation,
    candidate: ScheduledTripCandidate,
) -> MatchResult:
    score = 0.0
    reasons: list[str] = []

    if observation.route_id == candidate.route_id:
        score += 50
        reasons.append("route_id")
    else:
        return MatchResult(trip_id=None, score=0.0, reason="route mismatch")

    if observation.direction_id is not None and observation.direction_id == candidate.direction_id:
        score += 15
        reasons.append("direction_id")

    if observation.start_date and candidate.start_date and observation.start_date == candidate.start_date:
        score += 10
        reasons.append("start_date")

    if observation.start_time and candidate.start_time and observation.start_time == candidate.start_time:
        score += 15
        reasons.append("start_time")

    if observation.stop_id and candidate.next_stop_id and observation.stop_id == candidate.next_stop_id:
        score += 10
        reasons.append("stop_id")

    if candidate.shape_points:
        distance = shape_distance_meters(observation, candidate.shape_points)
        if distance <= 25:
            score += 25
        elif distance <= 75:
            score += 15
        elif distance <= 150:
            score += 5
        else:
            score -= 20
        reasons.append(f"shape_distance={round(distance, 1)}m")

    return MatchResult(trip_id=candidate.trip_id, score=score, reason=", ".join(reasons))


def select_best_match(
    observation: VehicleObservation,
    candidates: Iterable[ScheduledTripCandidate],
    minimum_score: float = 55.0,
) -> MatchResult:
    scored = [score_candidate(observation, candidate) for candidate in candidates]
    if not scored:
        return MatchResult(trip_id=None, score=0.0, reason="no candidates")
    best = max(scored, key=lambda result: result.score)
    if best.score < minimum_score:
        return MatchResult(trip_id=None, score=best.score, reason=f"below threshold: {best.reason}")
    return best

