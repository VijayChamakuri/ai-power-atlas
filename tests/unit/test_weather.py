from datetime import date

import httpx
import pytest

from atlas.ingest.weather import WeatherQuotaError, fetch_weather

# Body copied from Open-Meteo's real response on 2026-11-01.
DAILY_LIMIT = {
    "reason": "Daily API request limit exceeded. Please try again tomorrow.",
    "error": True,
}
DAY = date(2026, 10, 20)


def test_daily_limit_stops_at_once_with_a_way_forward() -> None:
    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json=DAILY_LIMIT)

    with (
        httpx.Client(transport=httpx.MockTransport(answer)) as client,
        pytest.raises(WeatherQuotaError, match="lake-restore"),
    ):
        fetch_weather(client, 39.77, -86.16, DAY, DAY)
    assert len(calls) == 1


def test_short_limit_is_waited_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_weather.retry, "sleep", lambda _: None)
    answers = [
        httpx.Response(429, json={"reason": "Minutely API request limit exceeded.", "error": True}),
        httpx.Response(
            200, json={"hourly": {"time": ["2026-10-20T00:00"], "temperature_2m": [50.0]}}
        ),
    ]
    with httpx.Client(transport=httpx.MockTransport(lambda _: answers.pop(0))) as client:
        frame = fetch_weather(client, 39.77, -86.16, DAY, DAY)
    assert list(frame["temperature_2m"]) == [50.0]
