"""Vision-Modul: Berechnung der günstigsten Strompreis-Zeitfenster.

Analysiert die Brutto-Spotpreise und berechnet:
- Aktueller Strompreis
- Günstigste Startzeit für einen konfigurierbaren Stunden-Block
- Günstigste Startzeit für einen Stunden-Block in der Nachtzeit (22-06 Uhr)

Ergebnisse werden in vision_db.json gespeichert.
"""

import json
import logging
import os
from datetime import datetime, timedelta

from tinydb import TinyDB

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ENV_DIR = os.path.join(BASE_DIR, "env")

SPOTPREIS_BRUTTO_DB = os.path.join(DATA_DIR, "spotpreise_brutto_db.json")
VISION_DB = os.path.join(DATA_DIR, "vision_db.json")
ACCOUNT_ENV = os.path.join(ENV_DIR, "account.env")

# Spotpreis-Intervall: 15 Minuten
INTERVALL_MIN = 15
EINTRAEGE_PRO_STUNDE = 60 // INTERVALL_MIN

# Nachtzeit (Durchschnitt Deutschland: Sonnenuntergang ~20:00, Sonnenaufgang ~07:00)
NACHT_START = 20
NACHT_ENDE = 7


def _read_stunden_block() -> int:
    """Liest den Stunden-Block aus account.env (min 1, Standard 2)."""
    try:
        with open(ACCOUNT_ENV, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("stunden_block="):
                    val = line.strip().split("=", 1)[1].strip('"')
                    return max(1, int(val))
    except (FileNotFoundError, ValueError, OSError):
        pass
    return 2


def _read_vorausschau_stunden() -> int:
    """Liest die Vorausschau-Stunden aus account.env (min = Zeitraum+1)."""
    try:
        stunden_block = _read_stunden_block()
        min_val = stunden_block + 1
        with open(ACCOUNT_ENV, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("vorausschau_stunden="):
                    val = line.strip().split("=", 1)[1].strip('"')
                    return max(min_val, int(val))
    except (FileNotFoundError, ValueError, OSError):
        pass
    return 12


def _read_nur_nacht() -> bool:
    """Liest den Nacht-Modus aus account.env."""
    try:
        with open(ACCOUNT_ENV, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("nur_nacht="):
                    val = line.strip().split("=", 1)[1].strip('"')
                    return val.lower() == "true"
    except (FileNotFoundError, ValueError, OSError):
        pass
    return False


def _lade_spotpreise() -> list[dict]:
    """Lädt Brutto-Spotpreise und gibt sortierte Liste zurück."""
    if not os.path.isfile(SPOTPREIS_BRUTTO_DB):
        _LOGGER.warning("Vision: Brutto-DB nicht vorhanden: %s", SPOTPREIS_BRUTTO_DB)
        return []

    try:
        with open(SPOTPREIS_BRUTTO_DB, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as err:
        _LOGGER.error("Vision: Fehler beim Lesen der Brutto-DB – %s", err)
        return []

    preise = []
    for entry in data.get("_default", {}).values():
        if "timestamp" not in entry or "price" not in entry:
            continue
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            preise.append({
                "timestamp": ts,
                "timestamp_str": entry["timestamp"],
                "price": entry["price"] / 1000,  # €/MWh → €/kWh
            })
        except (ValueError, TypeError):
            continue

    preise.sort(key=lambda x: x["timestamp"])
    return preise


def _finde_aktuellen_preis(preise: list[dict]) -> float | None:
    """Aktuellen 15-Min-Preis finden."""
    now = datetime.now().astimezone()
    for eintrag in preise:
        ts = eintrag["timestamp"]
        if ts <= now < ts + timedelta(minutes=INTERVALL_MIN):
            return round(eintrag["price"], 5)
    # Fallback: nächster zukünftiger Eintrag
    for eintrag in preise:
        if eintrag["timestamp"] >= now:
            return round(eintrag["price"], 5)
    return None


def _ist_nachtzeit(dt: datetime) -> bool:
    return dt.hour >= NACHT_START or dt.hour < NACHT_ENDE


def _finde_guenstigste_startzeit(
    preise: list[dict],
    stunden: int,
    nur_nacht: bool = False,
    max_vorausschau_h: int = 12,
) -> tuple[dict | None, float | None]:
    """Findet die günstigste zusammenhängende Startzeit.

    Der *Start* des Blocks muss innerhalb von max_vorausschau_h Stunden
    liegen.  Der Block selbst darf darüber hinausgehen.
    Bei nur_nacht=True werden nur Nacht-Zeitfenster (22–06 Uhr) betrachtet,
    die 12-h-Grenze gilt trotzdem für den Startpunkt.
    """
    anzahl = stunden * EINTRAEGE_PRO_STUNDE
    now = datetime.now().astimezone()
    grenze = now + timedelta(hours=max_vorausschau_h)

    future = [e for e in preise if e["timestamp"] >= now]
    if nur_nacht:
        future = [e for e in future if _ist_nachtzeit(e["timestamp"])]

    if len(future) < anzahl:
        return None, None

    min_avg = float("inf")
    min_start = None

    for i in range(len(future) - anzahl + 1):
        window = future[i : i + anzahl]

        # Startpunkt muss innerhalb der Vorausschau liegen
        if window[0]["timestamp"] >= grenze:
            continue

        # Prüfe Aufeinanderfolge (max 20 Min Abstand)
        consecutive = all(
            window[j + 1]["timestamp"] - window[j]["timestamp"] <= timedelta(minutes=20)
            for j in range(len(window) - 1)
        )
        if not consecutive:
            continue

        avg = sum(e["price"] for e in window) / anzahl
        if avg < min_avg:
            min_avg = avg
            min_start = window[0]

    if min_start is None:
        return None, None
    return min_start, min_avg


def run() -> bool:
    """Vision-Berechnung durchführen und in DB speichern."""
    stunden = _read_stunden_block()
    vorausschau = _read_vorausschau_stunden()
    nur_nacht = _read_nur_nacht()

    preise = _lade_spotpreise()
    if not preise:
        _LOGGER.info("Vision: Keine Spotpreise vorhanden – überspringe")
        return False

    aktueller_preis = _finde_aktuellen_preis(preise)

    start, avg = _finde_guenstigste_startzeit(
        preise, stunden, nur_nacht=nur_nacht, max_vorausschau_h=vorausschau
    )
    guenstigste_zeit = start["timestamp_str"] if start else None
    guenstigste_summe = round(avg, 5) if avg and avg != float("inf") else None

    result = {
        "device_id": "vision_strom",
        "timestamp": datetime.now().isoformat(),
        "aktueller_preis": aktueller_preis,
        "guenstigste_startzeit": guenstigste_zeit,
        "guenstigste_summe": guenstigste_summe,
        "stunden_block": stunden,
    }

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with TinyDB(VISION_DB) as db:
            db.truncate()
            db.insert(result)
        _LOGGER.info("Vision: Daten gespeichert (Preis: %s €/kWh)", aktueller_preis)
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Vision: Fehler beim Schreiben – %s", err)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
