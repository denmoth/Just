from typing import Optional

from core.search import (
    SearchResult, smart_score, switch_layout,
    EN_TO_RU, RU_TO_EN, _clipboard,
)
from core.config import CFG, _cached_api

_WEATHER_TRIGGERS = {
    "погода", "weather", "температура", "прогноз", "forecast",
    "temp", "на улице", "за окном", "climate",
}
_WMO_CODES = {
    0: ("Ясно", "weather-clear"),
    1: ("Малооблачно", "weather-few-clouds"),
    2: ("Облачно", "weather-clouds"),
    3: ("Пасмурно", "weather-overcast"),
    45: ("Туман", "weather-fog"), 48: ("Туман", "weather-fog"),
    51: ("Мелкий дождь", "weather-showers-scattered"),
    53: ("Дождь", "weather-showers"), 55: ("Сильный дождь", "weather-showers"),
    61: ("Дождь", "weather-showers"), 63: ("Дождь", "weather-showers"),
    65: ("Ливень", "weather-storm"),
    71: ("Лёгкий снег", "weather-snow-scattered"),
    73: ("Снег", "weather-snow"), 75: ("Сильный снег", "weather-snow"),
    77: ("Снежная крупа", "weather-snow"),
    80: ("Ливень", "weather-showers"), 81: ("Ливень", "weather-showers"),
    82: ("Ливень", "weather-storm"),
    85: ("Снегопад", "weather-snow"), 86: ("Снегопад", "weather-snow"),
    95: ("Гроза", "weather-storm"),
    96: ("Гроза с градом", "weather-storm"), 99: ("Гроза с градом", "weather-storm"),
}


def _get_location() -> Optional[tuple[float, float, str]]:
    data = _cached_api("location.json", "https://ipapi.co/json/", 86400)
    if data and "latitude" in data:
        city = data.get("city", data.get("region", ""))
        return float(data["latitude"]), float(data["longitude"]), city
    return None


def _hourly_rows(data: dict, limit: int = 18) -> list[dict]:
    h = data.get("hourly") or {}
    times = h.get("time") or []
    temps = h.get("temperature_2m") or []
    codes = h.get("weather_code") or []
    out: list[dict] = []
    if not times:
        return out
    for i in range(min(limit, len(times))):
        t = times[i]
        if "T" in t:
            short = t.split("T")[1][:5]
        else:
            short = t[-5:]
        tp = temps[i] if i < len(temps) else "?"
        cd = int(codes[i]) if i < len(codes) else 0
        desc, icon = _WMO_CODES.get(cd, ("—", "weather-none-available"))
        out.append({"time": short, "temp": tp, "desc": desc, "icon": icon})
    return out


class WeatherRunner:
    def match(self, query: str) -> list[SearchResult]:
        q = query.lower().strip()
        matched = False
        for v in (q, switch_layout(q, EN_TO_RU), switch_layout(q, RU_TO_EN)):
            for trigger in _WEATHER_TRIGGERS:
                if smart_score(v, trigger) > 0.5:
                    matched = True
                    break
            if matched:
                break
        if not matched:
            return []

        loc = _get_location()
        if not loc:
            return [SearchResult(
                title="Погода: не удалось определить местоположение",
                subtitle="Проверьте интернет-соединение",
                icon_name="weather-none-available", score=0.9,
                category="Погода", action=lambda: None,
            )]

        lat, lon, city = loc
        max_age = CFG.get("weather_cache_minutes", 60) * 60
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,apparent_temperature,weather_code,"
            f"wind_speed_10m,relative_humidity_2m,pressure_msl,cloud_cover"
            f"&hourly=temperature_2m,weather_code"
            f"&forecast_days=2"
            f"&timezone=auto"
        )
        data = _cached_api("weather.json", url, max_age)
        if not data or "current" not in data:
            return [SearchResult(
                title="Погода: нет данных",
                subtitle="Не удалось загрузить прогноз",
                icon_name="weather-none-available", score=0.9,
                category="Погода", action=lambda: None,
            )]

        cur = data["current"]
        temp = cur.get("temperature_2m", "?")
        feels = cur.get("apparent_temperature", "?")
        code = cur.get("weather_code", 0)
        wind = cur.get("wind_speed_10m", "?")
        humidity = cur.get("relative_humidity_2m", "?")
        pressure = cur.get("pressure_msl", "?")
        clouds = cur.get("cloud_cover", "?")

        desc, icon = _WMO_CODES.get(code, ("Неизвестно", "weather-none-available"))

        hourly = _hourly_rows(data)
        preview_plain = (
            f"{city}\n{temp}°C — {desc}\nОщущается {feels}°C · Ветер {wind} км/ч · "
            f"Влажность {humidity}% · Давление {pressure} гПа · Облачность {clouds}%"
        )

        preview_data = {
            "city": str(city),
            "temp": str(temp),
            "feels": str(feels),
            "desc": desc,
            "icon_name": icon,
            "wind": str(wind),
            "humidity": str(humidity),
            "pressure": str(pressure),
            "clouds": str(clouds),
            "hourly": hourly,
        }

        return [SearchResult(
            title=f"{city}: {temp}°C — {desc}",
            subtitle=(
                f"Ощущается {feels}°C · Ветер {wind} км/ч · Влажность {humidity}%"
            ),
            icon_name=icon, score=0.95,
            category="Погода",
            preview_kind="weather",
            preview_text=preview_plain,
            preview_data=preview_data,
            usage_key="weather:open",
            action=lambda: _clipboard(f"{temp}°C"),
        )]


RUNNERS = [WeatherRunner()]
