from collections.abc import Iterable
from statistics import mean


def classify_delay(delay_minutes: float, early_threshold: int, late_threshold: int) -> str:
    if delay_minutes < early_threshold:
        return "early"
    if delay_minutes > late_threshold:
        return "late"
    return "on_time"


def on_time_ratio(
    delay_minutes: Iterable[float],
    early_threshold: int,
    late_threshold: int,
) -> float:
    delays = list(delay_minutes)
    if not delays:
        return 0.0
    hits = sum(
        1
        for delay in delays
        if classify_delay(delay, early_threshold=early_threshold, late_threshold=late_threshold)
        == "on_time"
    )
    return round((hits / len(delays)) * 100, 2)


def average_delay(delay_minutes: Iterable[float]) -> float:
    delays = list(delay_minutes)
    if not delays:
        return 0.0
    return round(mean(delays), 2)

