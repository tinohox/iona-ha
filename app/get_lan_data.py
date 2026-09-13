"""Aktuelle Verbrauchsdaten von der lokalen iONA Box auslesen.

Kommuniziert über das lokale Netzwerk mit der iONA Box,
liest Momentanleistung (W), Gesamtverbrauch (kWh) und
Gesamteinspeisung (kWh) aus und schreibt in meter_db.json.
"""

import os
import ast
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from tinydb import TinyDB, Query

try:  # als Paket (Home Assistant)
    from .fetch_utils import (
        FetchResult,
        newest,
        ts_allows_update,
        value_allows_update,
    )
except ImportError:  # direkter Aufruf: python app/get_lan_data.py
    from fetch_utils import (  # type: ignore[no-redef]
        FetchResult,
        newest,
        ts_allows_update,
        value_allows_update,
    )

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "meter_db.json")

TZ_LOCAL = ZoneInfo("Europe/Berlin")

SOURCE = "LAN"


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


def _fetch_data(url: str, access_token: str) -> dict | None:
    """Verbrauchsdaten von der iONA Box abrufen."""
    headers = {
        "Authorization": f'N2G-LAN-USER token="{access_token}"',
        "accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 401:
            _LOGGER.warning("LAN-Daten: 401 – Token nicht gültig")
            return None
        if response.status_code == 200:
            return response.json()
        _LOGGER.warning("LAN-Daten: API-Fehler %d", response.status_code)
        return None
    except requests.RequestException as err:
        # Nur warning: läuft im 5-s-Takt; dauerhafte Ausfälle meldet der
        # DataManager per Notification (Edge-Trigger)
        _LOGGER.warning("LAN-Daten: Verbindungsfehler – %s", err)
        return None


def _parse_power(raw_value: int | None) -> int | None:
    """Momentanleistung korrigieren (Überlauf-Werte)."""
    if raw_value is None or raw_value == 0:
        return None
    if raw_value > 9_000_000:
        return raw_value - 16_777_216
    return raw_value


def _accept(key: str, entry: dict, new_value, new_ts) -> bool:
    """Prüft, ob ein Messwert den gespeicherten ersetzen darf.

    Zwei unabhängige Bedingungen: der Zeitstempel muss den Wert als neuer
    ausweisen (oder unvergleichbar sein), und bei Zählerständen darf der
    Wert nicht sinken.
    """
    if not ts_allows_update(new_ts, entry.get(f"{key}_timestamp")):
        return False
    if not value_allows_update(key, new_value, entry.get(key)):
        _LOGGER.warning(
            "LAN-Daten: %s würde von %s auf %s sinken – verworfen "
            "(Zählerstände dürfen nicht zurückgehen)",
            key, entry.get(key), new_value,
        )
        return False
    return True


def run() -> FetchResult:
    """Hauptfunktion: Daten von der iONA Box lesen und in DB schreiben."""
    # Zugangsdaten laden
    secrets = _read_env("secrets-n2g.env")
    iona_box = secrets.get("IONA_BOX")
    if not iona_box:
        _LOGGER.error("IONA_BOX nicht in secrets-n2g.env gesetzt")
        return FetchResult(False, source=SOURCE, error="IONA_BOX nicht gesetzt")

    lan_env = _read_env("LanToken.env")
    data_raw = lan_env.get("DATA")
    if not data_raw:
        _LOGGER.debug("LAN-Token (DATA) nicht vorhanden – überspringe")
        return FetchResult(False, source=SOURCE, error="LAN-Token fehlt")

    try:
        data_dict = ast.literal_eval(data_raw)
        access_token = data_dict["user_lan_token"]
    except (ValueError, KeyError, TypeError) as err:
        _LOGGER.error("LAN-Token Parsing fehlgeschlagen: %s", err)
        return FetchResult(False, source=SOURCE, error=f"LAN-Token unlesbar: {err}")

    # Daten abrufen (Erreichbarkeit deckt der Request-Timeout selbst ab)
    url = f"http://{iona_box}/meter/now"
    data = _fetch_data(url, access_token)
    if data is None:
        return FetchResult(False, source=SOURCE, error="Box nicht erreichbar")

    # Momentanleistung
    try:
        power_raw = data["elec"]["power"]["now"]["value"]
        power_ts_epoch = data["elec"]["power"]["now"]["time"]
    except (KeyError, TypeError):
        power_raw = None
        power_ts_epoch = None

    momentanleistung = _parse_power(power_raw)
    momentanleistung_ts = (
        datetime.fromtimestamp(power_ts_epoch, tz=TZ_LOCAL).isoformat()
        if power_ts_epoch
        else None
    )

    # Gesamtverbrauch (Import)
    try:
        import_raw = data["elec"]["import"]["now"]["value"]
        import_ts_epoch = data["elec"]["import"]["now"]["time"]
    except (KeyError, TypeError):
        import_raw = None
        import_ts_epoch = None

    gesamtverbrauch = import_raw / 1000 if import_raw not in (None, 0) else None
    gesamtverbrauch_ts = (
        datetime.fromtimestamp(import_ts_epoch, tz=TZ_LOCAL).isoformat()
        if import_ts_epoch
        else None
    )

    # Gesamteinspeisung (Export)
    try:
        export_raw = data["elec"]["export"]["now"]["value"]
        export_ts_epoch = data["elec"]["export"]["now"]["time"]
    except (KeyError, TypeError):
        export_raw = None
        export_ts_epoch = None

    gesamteinspeisung = export_raw / 1000 if export_raw not in (None, 0) else None
    gesamteinspeisung_ts = (
        datetime.fromtimestamp(export_ts_epoch, tz=TZ_LOCAL).isoformat()
        if export_ts_epoch
        else None
    )

    measurement_time = newest(
        momentanleistung_ts, gesamtverbrauch_ts, gesamteinspeisung_ts
    )

    # In TinyDB schreiben
    os.makedirs(DATA_DIR, exist_ok=True)
    Device = Query()

    if os.path.isfile(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, ValueError):
            _LOGGER.warning("meter_db.json ist beschädigt – wird neu erstellt")
            os.remove(DB_PATH)

    updated = False

    with TinyDB(DB_PATH) as db:
        result = db.search(Device.device_id == "Stromzaehler")
        if result:
            entry = result[0]

            if gesamtverbrauch is not None and _accept(
                "Gesamtverbrauch", entry, gesamtverbrauch, gesamtverbrauch_ts
            ):
                entry["Gesamtverbrauch"] = gesamtverbrauch
                entry["Gesamtverbrauch_timestamp"] = gesamtverbrauch_ts
                updated = True

            if gesamteinspeisung is not None and _accept(
                "Gesamteinspeisung", entry, gesamteinspeisung, gesamteinspeisung_ts
            ):
                entry["Gesamteinspeisung"] = gesamteinspeisung
                entry["Gesamteinspeisung_timestamp"] = gesamteinspeisung_ts
                updated = True

            if momentanleistung is not None and _accept(
                "Momentanleistung", entry, momentanleistung, momentanleistung_ts
            ):
                entry["Momentanleistung"] = momentanleistung
                entry["Momentanleistung_timestamp"] = momentanleistung_ts
                updated = True

            if updated:
                entry["source"] = SOURCE
                db.update(entry, Device.device_id == "Stromzaehler")
                _LOGGER.debug("LAN-Daten: DB aktualisiert (Quelle: LAN)")
        else:
            insert_data = {"device_id": "Stromzaehler", "source": SOURCE}
            if gesamtverbrauch is not None:
                insert_data.update(
                    Gesamtverbrauch=gesamtverbrauch,
                    Gesamtverbrauch_unit="kWh",
                    Gesamtverbrauch_timestamp=gesamtverbrauch_ts,
                )
            if momentanleistung is not None:
                insert_data.update(
                    Momentanleistung=momentanleistung,
                    Momentanleistung_unit="W",
                    Momentanleistung_timestamp=momentanleistung_ts,
                )
            if gesamteinspeisung is not None:
                insert_data.update(
                    Gesamteinspeisung=gesamteinspeisung,
                    Gesamteinspeisung_unit="kWh",
                    Gesamteinspeisung_timestamp=gesamteinspeisung_ts,
                )
            db.insert(insert_data)
            updated = True
            _LOGGER.info("LAN-Daten: Neuer Zähler-Eintrag erstellt")

    return FetchResult(
        True, updated=updated, source=SOURCE, measurement_time=measurement_time
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
