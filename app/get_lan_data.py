"""Aktuelle Verbrauchsdaten von der lokalen iONA Box auslesen.

Kommuniziert über das lokale Netzwerk mit der iONA Box,
liest Momentanleistung (W), Gesamtverbrauch (kWh) und
Gesamteinspeisung (kWh) aus und schreibt in meter_db.json.
"""

import os
import ast
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from tinydb import TinyDB, Query

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "meter_db.json")


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
        _LOGGER.error("LAN-Daten: Verbindungsfehler – %s", err)
        return None


def _parse_power(raw_value: int | None) -> int | None:
    """Momentanleistung korrigieren (Überlauf-Werte)."""
    if raw_value is None or raw_value == 0:
        return None
    if raw_value > 9_000_000:
        return raw_value - 16_777_216
    return raw_value


def run() -> bool:
    """Hauptfunktion: Daten von der iONA Box lesen und in DB schreiben."""
    # Zugangsdaten laden
    secrets = _read_env("secrets-n2g.env")
    iona_box = secrets.get("IONA_BOX")
    if not iona_box:
        _LOGGER.error("IONA_BOX nicht in secrets-n2g.env gesetzt")
        return False

    lan_env = _read_env("LanToken.env")
    data_raw = lan_env.get("DATA")
    if not data_raw:
        _LOGGER.debug("LAN-Token (DATA) nicht vorhanden – überspringe")
        return False

    try:
        data_dict = ast.literal_eval(data_raw)
        access_token = data_dict["user_lan_token"]
    except (ValueError, KeyError, TypeError) as err:
        _LOGGER.error("LAN-Token Parsing fehlgeschlagen: %s", err)
        return False

    # Erreichbarkeit prüfen
    import socket
    try:
        sock = socket.create_connection((iona_box, 80), timeout=3)
        sock.close()
        _LOGGER.info("iONA Box %s ist erreichbar", iona_box)
    except (socket.timeout, OSError) as err:
        _LOGGER.warning("iONA Box %s nicht erreichbar: %s", iona_box, err)
        return False

    # Daten abrufen
    url = f"http://{iona_box}/meter/now"
    data = _fetch_data(url, access_token)
    if data is None:
        return False

    # Zeitzone Europa/Berlin (MEZ/MESZ automatisch)
    tz_local = ZoneInfo("Europe/Berlin")

    # Momentanleistung
    try:
        power_raw = data["elec"]["power"]["now"]["value"]
        power_ts_epoch = data["elec"]["power"]["now"]["time"]
    except (KeyError, TypeError):
        power_raw = None
        power_ts_epoch = None

    momentanleistung = _parse_power(power_raw)
    momentanleistung_ts = (
        datetime.fromtimestamp(power_ts_epoch, tz=tz_local).isoformat()
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
        datetime.fromtimestamp(import_ts_epoch, tz=tz_local).isoformat()
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
        datetime.fromtimestamp(export_ts_epoch, tz=tz_local).isoformat()
        if export_ts_epoch
        else None
    )

    # In TinyDB schreiben
    os.makedirs(DATA_DIR, exist_ok=True)
    Device = Query()

    with TinyDB(DB_PATH) as db:
        result = db.search(Device.device_id == "Stromzaehler")
        if result:
            entry = result[0]
            updated = False

            if gesamtverbrauch is not None:
                old_ts = entry.get("Gesamtverbrauch_timestamp")
                if not old_ts or gesamtverbrauch_ts > old_ts:
                    entry["Gesamtverbrauch"] = gesamtverbrauch
                    entry["Gesamtverbrauch_timestamp"] = gesamtverbrauch_ts
                    updated = True

            if gesamteinspeisung is not None:
                old_ts = entry.get("Gesamteinspeisung_timestamp")
                old_val = entry.get("Gesamteinspeisung")
                if not old_ts or gesamteinspeisung_ts > old_ts:
                    if not (old_val and old_val > 0 and gesamteinspeisung == 0):
                        entry["Gesamteinspeisung"] = gesamteinspeisung
                        entry["Gesamteinspeisung_timestamp"] = gesamteinspeisung_ts
                        updated = True

            if momentanleistung is not None:
                old_ts = entry.get("Momentanleistung_timestamp")
                if not old_ts or momentanleistung_ts > old_ts:
                    entry["Momentanleistung"] = momentanleistung
                    entry["Momentanleistung_timestamp"] = momentanleistung_ts
                    updated = True

            if updated:
                entry["source"] = "LAN"
                db.update(entry, Device.device_id == "Stromzaehler")
                _LOGGER.debug("LAN-Daten: DB aktualisiert (Quelle: LAN)")
        else:
            insert_data = {"device_id": "Stromzaehler", "source": "LAN"}
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
            _LOGGER.info("LAN-Daten: Neuer Zähler-Eintrag erstellt")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
