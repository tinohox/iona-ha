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
    except requests.RequestException as err:
        _LOGGER.error("Tarifdaten: Fehler beim Abruf – %s", err)
        return False

    # 501 und 404 heißen hier nicht "Server kaputt": Der Endpunkt antwortet so,
    # wenn für das angemeldete Konto kein dynamischer Tarif hinterlegt ist.
    # Gemessen: mit gebuchtem Tarif kommt 200, ohne oder mit ungültigem Token
    # kommt 403 – ein 501 ist also nichts, was sich durch erneutes Anmelden
    # beheben ließe.
    if response.status_code in (404, 501):
        _LOGGER.warning(
            "Tarifdaten: enviaM liefert für dieses Konto keine dynamischen "
            "Preise (HTTP %d). Das ist zu erwarten, wenn kein Tarif "
            "'mein Strom Vision' gebucht ist – die Vision-Option lässt sich "
            "dann unter Einstellungen → Geräte & Dienste → iona-ha → Optionen "
            "abschalten.",
            response.status_code,
        )
        return False

    if response.status_code == 403:
        _LOGGER.warning(
            "Tarifdaten: Zugriff abgelehnt (HTTP 403) – der Web-Token ist "
            "vermutlich abgelaufen. Der nächste Versuch läuft automatisch."
        )
        return False

    try:
        response.raise_for_status()
    except requests.RequestException as err:
        _LOGGER.error("Tarifdaten: Fehler beim Abruf – %s", err)
        return False

    try:
        data = response.json()
    except ValueError as err:
        _LOGGER.error("Tarifdaten: Antwort ist kein gültiges JSON – %s", err)
        return False

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
