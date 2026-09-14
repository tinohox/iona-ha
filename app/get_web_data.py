"""Verbrauchsdaten über die Web-API (n2g-iona) abrufen.

Dient als Fallback, wenn die lokale iONA Box nicht erreichbar ist oder
veraltete Messwerte liefert. Schreibt in meter_db.json.

Wichtig: Der Zeitstempel der Cloud wird unverändert gespeichert. Sein
Format und seine Zeitzone sind nicht dokumentiert – würde man hier eine
Zeitzone annehmen und dabei falsch raten, verschöbe sich der Wert um den
Offset und blockierte je nach Richtung die LAN- oder die Web-Quelle für
genau diese Zeitspanne. Den Vergleich übernimmt deshalb
`fetch_utils.ts_allows_update`, das gemischte Zeitbasen erkennt.
"""

import os
import logging

import requests
from tinydb import TinyDB, Query

try:  # als Paket (Home Assistant)
    from .fetch_utils import (
        AtomicJSONStorage,
        FetchResult,
        newest,
        quarantine_corrupt_db,
        ts_allows_update,
        value_allows_update,
    )
except ImportError:  # direkter Aufruf: python app/get_web_data.py
    from fetch_utils import (  # type: ignore[no-redef]
        AtomicJSONStorage,
        FetchResult,
        newest,
        quarantine_corrupt_db,
        ts_allows_update,
        value_allows_update,
    )

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "meter_db.json")

CONSUMPTION_URL = "https://api.n2g-iona.net/v2/instantaneous"

SOURCE = "WEB"


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


def _accept(key: str, entry: dict, new_value, new_ts) -> bool:
    """Prüft, ob ein Messwert den gespeicherten ersetzen darf.

    Gleiche Regeln wie im LAN-Modul – auch die Cloud stempelt die Abrufzeit
    und nicht den Messzeitpunkt (ihr `current_summation` steht messbar still,
    während `timestamp` weiterläuft).
    """
    if entry.get(key) == new_value:
        return False
    if not ts_allows_update(new_ts, entry.get(f"{key}_timestamp")):
        _LOGGER.debug(
            "Web-Daten: %s verworfen – gespeicherter Zeitstempel %r ist nicht älter "
            "als %r",
            key, entry.get(f"{key}_timestamp"), new_ts,
        )
        return False
    if not value_allows_update(key, new_value, entry.get(key)):
        _LOGGER.debug(
            "Web-Daten: %s würde von %s auf %s sinken – verworfen "
            "(Zählerstände dürfen nicht zurückgehen)",
            key, entry.get(key), new_value,
        )
        return False
    return True


def run(lan_alive: bool = False) -> FetchResult:
    """Web-Verbrauchsdaten abrufen und in DB schreiben.

    `lan_alive` = die lokale Box antwortet gerade. Dann bleibt die
    Momentanleistung unangetastet: sie kommt über LAN sekundengenau, während
    der Cloud-Wert Minuten alt sein kann. Ohne diese Regel könnte ein
    Web-Abruf – etwa ausgelöst durch einen stehenden Zählerstand – den
    Live-Leistungswert durch einen alten ersetzen und nebenbei die
    Datenquelle auf WEB umstellen.
    """
    web_env = _read_env("WebToken.env")
    access_token = web_env.get("ACCESS_TOKEN")
    if not access_token:
        _LOGGER.error("Web-Daten: ACCESS_TOKEN nicht vorhanden")
        return FetchResult(False, source=SOURCE, error="ACCESS_TOKEN fehlt")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(CONSUMPTION_URL, headers=headers, timeout=15)
        if response.status_code == 401:
            _LOGGER.warning("Web-Daten: 401 – Token ungültig")
            return FetchResult(False, source=SOURCE, error="401 Token ungültig")
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as err:
        _LOGGER.error("Web-Daten: Fehler – %s", err)
        return FetchResult(False, source=SOURCE, error=str(err))

    try:
        elec = data["data"]["electricity"]
        momentanleistung = elec["power"]
        momentanleistung_ts = elec["timestamp"]
        gesamtverbrauch = elec["current_summation"] / 1000
        gesamtverbrauch_ts = elec["timestamp"]
    except (KeyError, TypeError, ZeroDivisionError) as err:
        _LOGGER.error("Web-Daten: Ungültiges Antwortformat – %s", err)
        return FetchResult(False, source=SOURCE, error=f"Antwortformat: {err}")

    # Format/Zeitzone des Cloud-Zeitstempels sind nicht dokumentiert – für die
    # Fehlersuche protokollieren, damit man ihn nicht raten muss.
    _LOGGER.debug(
        "Web-Daten: Zeitstempel aus der Cloud = %r (Typ %s)",
        momentanleistung_ts, type(momentanleistung_ts).__name__,
    )

    measurement_time = newest(momentanleistung_ts)

    # In TinyDB schreiben
    os.makedirs(DATA_DIR, exist_ok=True)
    Device = Query()

    quarantine_corrupt_db(DB_PATH)

    updated = False
    took_over = False

    with TinyDB(DB_PATH, storage=AtomicJSONStorage) as db:
        result = db.search(Device.device_id == "Stromzaehler")
        if result:
            entry = result[0]

            if _accept("Gesamtverbrauch", entry, gesamtverbrauch, gesamtverbrauch_ts):
                entry["Gesamtverbrauch"] = gesamtverbrauch
                entry["Gesamtverbrauch_timestamp"] = gesamtverbrauch_ts
                updated = True

            if not lan_alive and _accept(
                "Momentanleistung", entry, momentanleistung, momentanleistung_ts
            ):
                entry["Momentanleistung"] = momentanleistung
                entry["Momentanleistung_timestamp"] = momentanleistung_ts
                updated = True
                took_over = True

            if updated:
                # source wechselt nur, wenn WEB die Führung übernimmt. Eine
                # reine Zählerstand-Korrektur bei laufendem LAN lässt sie auf
                # LAN – sonst spränge der Sensor im Minutentakt hin und her,
                # das Badge der Card mit, und Automationen auf state == 'WEB'
                # feuerten dauernd.
                if took_over:
                    entry["source"] = SOURCE
                db.update(entry, Device.device_id == "Stromzaehler")
                _LOGGER.debug("Web-Daten: DB aktualisiert (Quelle: WEB)")
        else:
            db.insert({
                "device_id": "Stromzaehler",
                "source": SOURCE,
                "Gesamtverbrauch": gesamtverbrauch,
                "Gesamtverbrauch_unit": "kWh",
                "Gesamtverbrauch_timestamp": gesamtverbrauch_ts,
                "Momentanleistung": momentanleistung,
                "Momentanleistung_unit": "W",
                "Momentanleistung_timestamp": momentanleistung_ts,
            })
            updated = True
            took_over = True
            _LOGGER.info("Web-Daten: Neuer Eintrag erstellt")

    return FetchResult(
        True, updated=updated, source=SOURCE, measurement_time=measurement_time
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
