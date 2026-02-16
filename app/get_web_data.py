"""Verbrauchsdaten über die Web-API (n2g-iona) abrufen.

Dient als Fallback, wenn die lokale iONA Box nicht erreichbar ist.
Schreibt in meter_db.json.
"""

import os
import logging
import requests
from tinydb import TinyDB, Query

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "meter_db.json")

CONSUMPTION_URL = "https://api.n2g-iona.net/v2/instantaneous"


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
    """Web-Verbrauchsdaten abrufen und in DB schreiben."""
    web_env = _read_env("WebToken.env")
    access_token = web_env.get("ACCESS_TOKEN")
    if not access_token:
        _LOGGER.error("Web-Daten: ACCESS_TOKEN nicht vorhanden")
        return False

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(CONSUMPTION_URL, headers=headers, timeout=15)
        if response.status_code == 401:
            _LOGGER.warning("Web-Daten: 401 – Token ungültig")
            return False
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as err:
        _LOGGER.error("Web-Daten: Fehler – %s", err)
        return False

    try:
        elec = data["data"]["electricity"]
        momentanleistung = elec["power"]
        momentanleistung_ts = elec["timestamp"]
        gesamtverbrauch = elec["current_summation"] / 1000
        gesamtverbrauch_ts = elec["timestamp"]
    except (KeyError, TypeError, ZeroDivisionError) as err:
        _LOGGER.error("Web-Daten: Ungültiges Antwortformat – %s", err)
        return False

    # In TinyDB schreiben
    os.makedirs(DATA_DIR, exist_ok=True)
    Device = Query()

    with TinyDB(DB_PATH) as db:
        result = db.search(Device.device_id == "Stromzaehler")
        if result:
            entry = result[0]
            updated = False

            old_ts = entry.get("Gesamtverbrauch_timestamp")
            if not old_ts or gesamtverbrauch_ts > old_ts:
                entry["Gesamtverbrauch"] = gesamtverbrauch
                entry["Gesamtverbrauch_timestamp"] = gesamtverbrauch_ts
                updated = True

            old_ts = entry.get("Momentanleistung_timestamp")
            if not old_ts or momentanleistung_ts > old_ts:
                entry["Momentanleistung"] = momentanleistung
                entry["Momentanleistung_timestamp"] = momentanleistung_ts
                updated = True

            if updated:
                entry["source"] = "WEB"
                db.update(entry, Device.device_id == "Stromzaehler")
                _LOGGER.debug("Web-Daten: DB aktualisiert (Quelle: WEB)")
        else:
            db.insert({
                "device_id": "Stromzaehler",
                "source": "WEB",
                "Gesamtverbrauch": gesamtverbrauch,
                "Gesamtverbrauch_unit": "kWh",
                "Gesamtverbrauch_timestamp": gesamtverbrauch_ts,
                "Momentanleistung": momentanleistung,
                "Momentanleistung_unit": "W",
                "Momentanleistung_timestamp": momentanleistung_ts,
            })
            _LOGGER.info("Web-Daten: Neuer Eintrag erstellt")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
