"""Gemeinsame Utility-Funktionen für .env Dateiverwaltung.

Zentralisiert alle Lese-/Schreiboperationen für .env Dateien,
damit keine doppelte Logik in verschiedenen Modulen existiert.
"""

import os
import shutil
import logging

_LOGGER = logging.getLogger(__name__)

# Pfade relativ zu diesem Modul
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_DIR = os.path.join(_BASE_DIR, "app", "env")

# Dateinamen (nach Migration von "accound" → "account")
ACCOUNT_ENV = "account.env"
SECRETS_ENV = "secrets-n2g.env"
LAN_TOKEN_ENV = "LanToken.env"
WEB_TOKEN_ENV = "WebToken.env"

# Legacy-Dateiname (Tippfehler in v1.x)
_LEGACY_ACCOUNT_ENV = "accound.env"


def get_env_path(filename: str) -> str:
    """Gibt den absoluten Pfad zu einer .env Datei zurück."""
    return os.path.join(ENV_DIR, filename)


def migrate_env_files() -> None:
    """Migriert alte Dateinamen (accound.env → account.env).

    Wird einmalig beim Start aufgerufen und benennt die Datei
    nur um, wenn die neue noch nicht existiert.
    """
    old_path = get_env_path(_LEGACY_ACCOUNT_ENV)
    new_path = get_env_path(ACCOUNT_ENV)

    if os.path.exists(old_path) and not os.path.exists(new_path):
        try:
            shutil.move(old_path, new_path)
            _LOGGER.info("Migration: %s → %s", _LEGACY_ACCOUNT_ENV, ACCOUNT_ENV)
        except OSError as err:
            _LOGGER.error("Migration fehlgeschlagen: %s", err)


def read_env_file(filename: str) -> dict:
    """Liest eine .env Datei und gibt ein dict zurück.

    Ignoriert Kommentare (#) und leere Zeilen.
    Entfernt umschließende Anführungszeichen von Werten.
    """
    env: dict[str, str] = {}
    filepath = get_env_path(filename)
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"')
    except FileNotFoundError:
        pass
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Fehler beim Lesen von %s: %s", filename, err)
    return env


def write_env_file(filename: str, data: dict) -> bool:
    """Schreibt ein dict als .env Datei.

    Erstellt das Verzeichnis, falls es nicht existiert.
    Werte werden in Anführungszeichen geschrieben.
    """
    filepath = get_env_path(filename)
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        lines = []
        for key, value in data.items():
            if value is not None:
                lines.append(f'{key}="{value}"')
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Fehler beim Schreiben von %s: %s", filename, err)
        return False


def read_env_value(filename: str, key: str, default: str | None = None) -> str | None:
    """Liest einen einzelnen Wert aus einer .env Datei."""
    return read_env_file(filename).get(key, default)


def env_file_exists(filename: str) -> bool:
    """Prüft ob eine .env Datei existiert und nicht leer ist."""
    filepath = get_env_path(filename)
    try:
        return os.path.isfile(filepath) and os.path.getsize(filepath) > 0
    except OSError:
        return False


# ---------- Häufig gebrauchte Konfigurationshelfer ----------


def is_vision_enabled() -> bool:
    """Prüft ob der dynamische Tarif (mein Strom Vision) aktiviert ist."""
    return read_env_value(ACCOUNT_ENV, "vision_tariff", "False").lower() == "true"


def get_stunden_block() -> int:
    """Gibt den konfigurierten Stunden-Block (1-8) zurück."""
    try:
        val = int(read_env_value(ACCOUNT_ENV, "stunden_block", "2"))
        return max(1, min(8, val))
    except (ValueError, TypeError):
        return 2


def set_stunden_block(value: int) -> bool:
    """Setzt den Stunden-Block in der account.env."""
    data = read_env_file(ACCOUNT_ENV)
    data["stunden_block"] = str(max(1, min(8, int(value))))
    return write_env_file(ACCOUNT_ENV, data)


def get_vorausschau_stunden() -> int:
    """Gibt die konfigurierte Vorausschau in Stunden (10-48) zurück."""
    try:
        val = int(read_env_value(ACCOUNT_ENV, "vorausschau_stunden", "12"))
        return max(10, min(48, val))
    except (ValueError, TypeError):
        return 12


def set_vorausschau_stunden(value: int) -> bool:
    """Setzt die Vorausschau-Stunden in der account.env."""
    data = read_env_file(ACCOUNT_ENV)
    data["vorausschau_stunden"] = str(max(10, min(48, int(value))))
    return write_env_file(ACCOUNT_ENV, data)


def get_nur_nacht() -> bool:
    """Gibt zurück ob nur Nachtzeiten gesucht werden sollen."""
    return read_env_value(ACCOUNT_ENV, "nur_nacht", "False").lower() == "true"


def set_nur_nacht(value: bool) -> bool:
    """Setzt den Nacht-Modus in der account.env."""
    data = read_env_file(ACCOUNT_ENV)
    data["nur_nacht"] = str(value)
    return write_env_file(ACCOUNT_ENV, data)


def get_secrets() -> dict:
    """Gibt die Zugangsdaten als dict zurück (IONA_BOX, USERNAME, PASSWORD)."""
    return read_env_file(SECRETS_ENV)


def get_web_token() -> str | None:
    """Gibt den aktuellen Web-API Access Token zurück oder None."""
    return read_env_value(WEB_TOKEN_ENV, "ACCESS_TOKEN")


def get_lan_token_data() -> str | None:
    """Gibt die rohen LAN-Token-Daten zurück oder None."""
    return read_env_value(LAN_TOKEN_ENV, "DATA")
