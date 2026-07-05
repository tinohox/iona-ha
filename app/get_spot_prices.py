"""Spotpreise von der enviaM-API abrufen und speichern.

Holt aktuelle Strompreise (Spotmarkt) für 2 Tage und speichert
sie als TinyDB-kompatibles JSON in spotpreise_db.json.
"""

import os
import json
import logging
import requests

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "spotpreise_db.json")

SPOT_URL = "https://api.enviam.de/shared/v2/enviaM/service/eex/v1/spotPrices"


def _read_env(filename: str) -> dict:
    env: dict[str, str] = {}
    filepath = os.path.join(ENV_DIR, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"')
    except FileNotFoundError:
        pass
    return env


def run() -> bool:
    """Spotpreise abrufen und speichern. Gibt True bei Erfolg zurück."""
    web_env = _read_env("WebToken.env")
    token = web_env.get("ACCESS_TOKEN")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "x-identity": "net2grid",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {"timeSlice": "twodays"}

    try:
        response = requests.get(SPOT_URL, params=params, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as err:
        _LOGGER.error("Spotpreise: Fehler beim Abruf – %s", err)
        return False

    data = response.json()
    price_points = data.get("pricePoints", [])

    if not price_points:
        _LOGGER.warning("Spotpreise: Keine Preisdaten in der Antwort")
        return False

    spotpreise = {"_default": {}}
    for idx, point in enumerate(price_points, start=1):
        spotpreise["_default"][str(idx)] = {
            "timestamp": point.get("timestamp"),
            "price": point.get("price"),
        }

    # Atomar speichern (tmp + rename)
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_path = DB_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(spotpreise, fh, ensure_ascii=False)
    os.replace(tmp_path, DB_PATH)

    _LOGGER.info("Spotpreise: %d Einträge gespeichert", len(price_points))
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
