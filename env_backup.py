"""Backup-Modul für .env Dateien.

Verwaltet regelmäßige Backups des env/ Verzeichnisses.
Backups werden im Home Assistant .storage Verzeichnis gespeichert,
das von HACS-Updates nicht betroffen ist.
"""

import os
import shutil
import logging

_LOGGER = logging.getLogger(__name__)


def get_backup_dir(hass):
    """Gibt den Pfad zum Backup-Verzeichnis zurück."""
    backup_dir = os.path.join(hass.config.path(".storage"), "iona_env_backup")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def restore_env_from_backup(hass) -> bool:
    """Stellt env/ aus dem Backup wieder her, wenn es leer ist.

    Wird beim Start der Integration aufgerufen, um nach einem
    HACS-Update die gelöschten .env Dateien wiederherzustellen.
    """
    env_dir = os.path.join(os.path.dirname(__file__), "app", "env")
    backup_dir = get_backup_dir(hass)

    if not os.path.exists(env_dir):
        os.makedirs(env_dir, exist_ok=True)

    # Prüfe ob env/ leer ist (ignoriere .gitkeep)
    env_files = [
        f
        for f in os.listdir(env_dir)
        if os.path.isfile(os.path.join(env_dir, f)) and f != ".gitkeep"
    ]

    if env_files:
        return False  # Dateien vorhanden, nichts zu tun

    if not os.path.exists(backup_dir):
        return False

    backup_files = [
        f
        for f in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, f)) and f != ".gitkeep"
    ]

    if not backup_files:
        return False

    try:
        for filename in backup_files:
            src = os.path.join(backup_dir, filename)
            dst = os.path.join(env_dir, filename)
            shutil.copy2(src, dst)
        _LOGGER.info(
            "env/ Dateien aus Backup wiederhergestellt: %d Dateien", len(backup_files)
        )
        return True
    except OSError as err:
        _LOGGER.error("Fehler beim Wiederherstellen aus Backup: %s", err)
        return False


def backup_env_files(hass) -> bool:
    """Erstellt ein Backup aller .env Dateien.

    Wird stündlich im Hintergrund aufgerufen.
    """
    env_dir = os.path.join(os.path.dirname(__file__), "app", "env")
    backup_dir = get_backup_dir(hass)

    if not os.path.exists(env_dir):
        return False

    try:
        # Alte Backups entfernen
        for filename in os.listdir(backup_dir):
            if filename == ".gitkeep":
                continue
            filepath = os.path.join(backup_dir, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)

        # Neue Dateien sichern
        count = 0
        for filename in os.listdir(env_dir):
            if filename == ".gitkeep":
                continue
            src = os.path.join(env_dir, filename)
            if os.path.isfile(src) and filename.endswith(".env"):
                shutil.copy2(src, os.path.join(backup_dir, filename))
                count += 1

        if count > 0:
            _LOGGER.debug("Backup erstellt: %d .env Dateien", count)
        return True

    except OSError as err:
        _LOGGER.error("Fehler beim Backup: %s", err)
        return False

