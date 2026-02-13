"""Tarifdaten von der enviaM-API abrufen und speichern.

Holt die aktuellen dynamischen Preiskomponenten (Arbeitspreis,
Netzentgelt, Umlagen, Steuern) und speichert sie in tariff_db.json.
"""

import os
import json
import logging
import requests

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "tariff_db.json")

TARIFF_URL = "https://api.enviam.de/shared/v2/enviaM/service/account/v1/dynamic/prices"


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
    """Tarifdaten abrufen und speichern. Gibt True bei Erfolg zurück."""
    web_env = _read_env("WebToken.env")
    token = web_env.get("ACCESS_TOKEN")

    headers = {
        "Accept": "application/json, text/plain, */*",
        "x-identity": "net2grid",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(TARIFF_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as err:
        _LOGGER.error("Tarifdaten: Fehler beim Abruf – %s", err)
        return False

    data = response.json()

    # Atomar speichern
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp_path = DB_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp_path, DB_PATH)

    _LOGGER.info("Tarifdaten gespeichert")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
