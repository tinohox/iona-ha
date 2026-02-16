"""Web-Token von der iONA/enviaM Auth-API holen und speichern.

Liest Zugangsdaten aus secrets-n2g.env, authentifiziert sich
und speichert den erhaltenen Token in WebToken.env.
"""

import os
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(BASE_DIR, "env")

AUTH_URL = "https://webapp.iona-energy.com/auth"


def _read_env(filename: str) -> dict:
    """Liest eine .env Datei als dict (ohne os.environ zu verändern)."""
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
    """Speichert Token-Daten in WebToken.env."""
    filepath = os.path.join(ENV_DIR, "WebToken.env")
    os.makedirs(ENV_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        for key, value in token_data.items():
            fh.write(f"{key.upper()}={value}\n")
    _LOGGER.debug("Web-Token gespeichert in %s", filepath)


def run() -> bool:
    """Hole einen neuen Web-Token. Gibt True bei Erfolg zurück."""
    secrets = _read_env("secrets-n2g.env")
    username = secrets.get("USERNAME")
    password = secrets.get("PASSWORD")

    if not username or not password:
        _LOGGER.error("USERNAME/PASSWORD nicht in secrets-n2g.env gesetzt")
        return False

    data = {"method": "login", "username": username, "password": password}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            AUTH_URL, headers=headers, json=data, verify=False, timeout=15
        )
        response.raise_for_status()
        token_data = response.json()
        _save_token(token_data)
        _LOGGER.info("Neuer Web-Token erfolgreich gespeichert")
        return True
    except requests.RequestException as err:
        _LOGGER.error("Fehler beim Web-Token-Abruf: %s", err)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run()
    raise SystemExit(0 if success else 1)
