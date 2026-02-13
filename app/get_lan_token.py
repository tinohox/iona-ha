"""LAN-Token für die iONA Box über die Web-API generieren und speichern.

Benötigt einen gültigen Web-Token (WebToken.env).
Speichert das Ergebnis in LanToken.env.
"""

import os
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")

LAN_TOKEN_URL = "https://api.n2g-iona.net/v2/lan/token"


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


def _save_token(token_data: dict) -> None:
    filepath = os.path.join(ENV_DIR, "LanToken.env")
    os.makedirs(ENV_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        for key, value in token_data.items():
            fh.write(f"{key.upper()}={value}\n")
    _LOGGER.debug("LAN-Token gespeichert in %s", filepath)


def run() -> bool:
    """Hole einen neuen LAN-Token. Gibt True bei Erfolg zurück."""
    web_env = _read_env("WebToken.env")
    access_token = web_env.get("ACCESS_TOKEN")

    if not access_token:
        _LOGGER.error("ACCESS_TOKEN nicht in WebToken.env gesetzt")
        return False

    headers = {"authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(LAN_TOKEN_URL, headers=headers, timeout=15)
        if response.status_code == 401:
            _LOGGER.warning("LAN-Token: 401 – Web-Token ungültig")
            return False
        response.raise_for_status()
        _save_token(response.json())
        _LOGGER.info("Neuer LAN-Token erfolgreich gespeichert")
        return True
    except requests.RequestException as err:
        _LOGGER.error("Fehler beim LAN-Token-Abruf: %s", err)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() else 1)
