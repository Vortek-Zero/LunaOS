#!/usr/bin/env python3
"""
actions/weather.py — Clima via wttr.in (sem chave de API).
"""
import re
import urllib.request
import urllib.parse
import json
from typing import Optional


class WeatherManager:
    def __init__(self):
        self._cache: dict[str, dict] = {}  # city → {data, ts}

    def get_weather(self, city: str = "") -> str:
        """Busca clima atual. Se city vazio, usa localização automática via IP."""
        import time
        cache_key = city or "_auto"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 1800:  # 30min TTL
            return cached["data"]

        location = urllib.parse.quote(city) if city else ""
        url = f"https://wttr.in/{location}?format=j1&lang=pt"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LunaAI/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            result = self._format(data, city)
            self._cache[cache_key] = {"data": result, "ts": time.time()}
            return result
        except Exception as e:
            return f"Não consegui obter o clima agora. ({e})"

    def _format(self, data: dict, city: str) -> str:
        try:
            current = data["current_condition"][0]
            area = data["nearest_area"][0]
            city_name = city or area["areaName"][0]["value"]
            country = area["country"][0]["value"]

            temp_c = current["temp_C"]
            feels = current["FeelsLikeC"]
            desc = current["lang_pt"][0]["value"] if current.get("lang_pt") else current["weatherDesc"][0]["value"]
            humidity = current["humidity"]
            wind_kmph = current["windspeedKmph"]

            # Previsão de hoje
            today = data["weather"][0]
            max_c = today["maxtempC"]
            min_c = today["mintempC"]

            # Chuva
            rain_chance = today["hourly"][4].get("chanceofrain", "0")

            result = (
                f"🌤 Clima em {city_name}, {country}:\n"
                f"  Agora: {temp_c}°C (sensação {feels}°C) — {desc}\n"
                f"  Hoje: mín {min_c}°C / máx {max_c}°C\n"
                f"  Umidade: {humidity}% | Vento: {wind_kmph} km/h"
            )
            if int(rain_chance) > 30:
                result += f"\n  ☔ Chance de chuva: {rain_chance}%"
            return result
        except Exception:
            return "Não consegui interpretar os dados do clima."

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()
        if not any(w in tl for w in ["tempo", "clima", "temperatura", "chuva", "previsão", "previsao", "vai chover"]):
            return None

        # Extrai cidade — busca no texto original para preservar maiúsculas
        m = re.search(r'(?:em|de|para|no|na)\s+([A-ZÀ-Úa-zà-ú][a-zà-ú]+(?:\s+[A-ZÀ-Úa-zà-ú][a-zà-ú]+)*)', text, re.IGNORECASE)
        city = m.group(1).strip() if m else ""
        return self.get_weather(city)


# Singleton
_weather_instance: Optional[WeatherManager] = None

def get_weather() -> WeatherManager:
    global _weather_instance
    if _weather_instance is None:
        _weather_instance = WeatherManager()
    return _weather_instance
