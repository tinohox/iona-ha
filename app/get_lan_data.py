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

try:  # als Paket (Home Assistant)
    from .fetch_utils import (
        AtomicJSONStorage,
        ERR_AUTH,
        ERR_CONFIG,
        ERR_HTTP,
        ERR_UNREACHABLE,
        FetchResult,
        newest,
        quarantine_corrupt_db,
        ts_allows_update,
        value_allows_update,
    )
except ImportError:  # direkter Aufruf: python app/get_lan_data.py
    from fetch_utils import (  # type: ignore[no-redef]
        AtomicJSONStorage,
        ERR_AUTH,
        ERR_CONFIG,
        ERR_HTTP,
        ERR_UNREACHABLE,
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


def _fetch_data(url: str, access_token: str) -> tuple[dict | None, str | None]:
    """Verbrauchsdaten von der iONA Box abrufen.

    Liefert (Daten, Fehlerursache). Die Ursache wird bis zur Benachrichtigung
    durchgereicht – ein 401 bedeutet etwas völlig anderes als ein Timeout.
    """
    headers = {
        "Authorization": f'N2G-LAN-USER token="{access_token}"',
        "accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 401:
            _LOGGER.debug("LAN-Daten: 401 – Token nicht gültig")
            return None, ERR_AUTH
        if response.status_code == 200:
            return response.json(), None
        _LOGGER.debug("LAN-Daten: API-Fehler %d", response.status_code)
        return None, ERR_HTTP
    except requests.RequestException as err:
        # debug, nicht warning: Der Abruf läuft im 5-Sekunden-Takt, eine
        # dauerhaft abwesende Box erzeugte sonst rund 17 000 Meldungen pro
        # Tag. Den Zustandswechsel meldet der DataManager einmalig auf INFO
        # und schickt eine ursachenabhängige Benachrichtigung.
        _LOGGER.debug("LAN-Daten: Verbindungsfehler – %s", err)
        return None, ERR_UNREACHABLE


def _parse_power(raw_value: int | None) -> int | None:
    """Momentanleistung korrigieren (Überlauf-Werte)."""
    if raw_value is None or raw_value == 0:
        return None
    if raw_value > 9_000_000:
        return raw_value - 16_777_216
    return raw_value


def _accept(key: str, entry: dict, new_value, new_ts, rejected: list) -> bool:
    """Prüft, ob ein Messwert den gespeicherten ersetzen darf.

    Drei Bedingungen, in dieser Reihenfolge:

    1. Der Wert muss sich tatsächlich unterscheiden. Die Box stempelt jeden
       Messwert mit der **Abrufzeit**, nicht mit dem Messzeitpunkt – eine
       eingefrorene Box liefert also unverändert dieselben Werte mit immer
       neuem `time`. Würde man das schreiben, sähe jeder Stillstand wie ein
       frischer Messwert aus, und weder das Log noch der Web-Fallback könnten
       ihn je bemerken. Bleibt der Wert gleich, bleibt deshalb auch sein
       Zeitstempel stehen; er bedeutet damit "seit wann steht dieser Wert".
    2. Der Zeitstempel muss den Wert als neuer ausweisen (oder unvergleichbar
       sein).
    3. Zählerstände dürfen nicht sinken.
    """
    if entry.get(key) == new_value:
        return False
    if not ts_allows_update(new_ts, entry.get(f"{key}_timestamp")):
        return False
    if not value_allows_update(key, new_value, entry.get(key)):
        # Bewusst debug: Sobald die Cloud einmal einen höheren Zählerstand
        # geschrieben hat, wird der niedrigere LAN-Wert im 5-Sekunden-Takt
        # abgelehnt. Als warning wären das rund 17 000 Meldungen pro Tag,
        # ausgerechnet bei dem Nutzer, dem gerade geholfen wird. Den Zustand
        # meldet der DataManager einmalig beim Wechsel.
        _LOGGER.debug(
            "LAN-Daten: %s würde von %s auf %s sinken – verworfen "
            "(Zählerstände dürfen nicht zurückgehen)",
            key, entry.get(key), new_value,
        )
        rejected.append(key)
        return False
    return True


def run() -> FetchResult:
    """Hauptfunktion: Daten von der iONA Box lesen und in DB schreiben."""
    # Zugangsdaten laden
    secrets = _read_env("secrets-n2g.env")
    iona_box = secrets.get("IONA_BOX")
    if not iona_box:
        _LOGGER.error("IONA_BOX nicht in secrets-n2g.env gesetzt")
        return FetchResult(False, source=SOURCE, error=ERR_CONFIG)

    lan_env = _read_env("LanToken.env")
    data_raw = lan_env.get("DATA")
    if not data_raw:
        _LOGGER.debug("LAN-Token (DATA) nicht vorhanden – überspringe")
        return FetchResult(False, source=SOURCE, error=ERR_CONFIG)

    try:
        data_dict = ast.literal_eval(data_raw)
        access_token = data_dict["user_lan_token"]
    except (ValueError, KeyError, TypeError) as err:
        _LOGGER.error("LAN-Token Parsing fehlgeschlagen: %s", err)
        return FetchResult(False, source=SOURCE, error=ERR_CONFIG)

    # Daten abrufen (Erreichbarkeit deckt der Request-Timeout selbst ab)
    url = f"http://{iona_box}/meter/now"
    data, reason = _fetch_data(url, access_token)
    if data is None:
        return FetchResult(False, source=SOURCE, error=reason)

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

    quarantine_corrupt_db(DB_PATH)

    updated = False
    rejected: list[str] = []

    with TinyDB(DB_PATH, storage=AtomicJSONStorage) as db:
        result = db.search(Device.device_id == "Stromzaehler")
        if result:
            entry = result[0]

            if gesamtverbrauch is not None and _accept(
                "Gesamtverbrauch", entry, gesamtverbrauch, gesamtverbrauch_ts, rejected
            ):
                entry["Gesamtverbrauch"] = gesamtverbrauch
                entry["Gesamtverbrauch_timestamp"] = gesamtverbrauch_ts
                updated = True

            if gesamteinspeisung is not None and _accept(
                "Gesamteinspeisung", entry, gesamteinspeisung, gesamteinspeisung_ts, rejected
            ):
                entry["Gesamteinspeisung"] = gesamteinspeisung
                entry["Gesamteinspeisung_timestamp"] = gesamteinspeisung_ts
                updated = True

            if momentanleistung is not None and _accept(
                "Momentanleistung", entry, momentanleistung, momentanleistung_ts, rejected
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
        True,
        updated=updated,
        source=SOURCE,
        measurement_time=measurement_time,
        rejected_decrease=bool(rejected),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
