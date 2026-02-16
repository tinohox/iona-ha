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


def get_data_backup_dir(hass):
    """Gibt den Pfad zum Daten-Backup-Verzeichnis zurück."""
    backup_dir = os.path.join(hass.config.path(".storage"), "iona_data_backup")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def restore_env_from_backup(hass) -> bool:
    """Stellt env/ und data/ aus dem Backup wieder her.

    Wird beim Start der Integration aufgerufen, um nach einem
    HACS-Update die gelöschten Dateien wiederherzustellen.
    """
    restored = False

    # --- env/ wiederherstellen ---
    env_dir = os.path.join(os.path.dirname(__file__), "app", "env")
    backup_dir = get_backup_dir(hass)

    if not os.path.exists(env_dir):
        os.makedirs(env_dir, exist_ok=True)

    env_files = [
        f
        for f in os.listdir(env_dir)
        if os.path.isfile(os.path.join(env_dir, f)) and f != ".gitkeep"
    ]

    if not env_files and os.path.exists(backup_dir):
        backup_files = [
            f
            for f in os.listdir(backup_dir)
            if os.path.isfile(os.path.join(backup_dir, f)) and f != ".gitkeep"
        ]
        if backup_files:
            try:
                for filename in backup_files:
                    src = os.path.join(backup_dir, filename)
                    dst = os.path.join(env_dir, filename)
                    shutil.copy2(src, dst)
                _LOGGER.info(
                    "env/ Dateien aus Backup wiederhergestellt: %d Dateien",
                    len(backup_files),
                )
                restored = True
            except OSError as err:
                _LOGGER.error("Fehler beim Wiederherstellen von env/: %s", err)

    # --- data/ wiederherstellen ---
    data_dir = os.path.join(os.path.dirname(__file__), "app", "data")
    data_backup_dir = get_data_backup_dir(hass)

    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    data_files = [
        f
        for f in os.listdir(data_dir)
        if os.path.isfile(os.path.join(data_dir, f))
        and f.endswith(".json")
    ]

    if not data_files and os.path.exists(data_backup_dir):
        backup_data_files = [
            f
            for f in os.listdir(data_backup_dir)
            if os.path.isfile(os.path.join(data_backup_dir, f))
            and f.endswith(".json")
        ]
        if backup_data_files:
            try:
                for filename in backup_data_files:
                    src = os.path.join(data_backup_dir, filename)
                    dst = os.path.join(data_dir, filename)
                    shutil.copy2(src, dst)
                _LOGGER.info(
                    "data/ Dateien aus Backup wiederhergestellt: %d Dateien",
                    len(backup_data_files),
                )
                restored = True
            except OSError as err:
                _LOGGER.error("Fehler beim Wiederherstellen von data/: %s", err)

    return restored


def backup_env_files(hass) -> bool:
    """Erstellt ein Backup aller .env und .json Datendateien.

    Wird stündlich im Hintergrund aufgerufen.
    Sichert env/ → .storage/iona_env_backup/
    Sichert data/ → .storage/iona_data_backup/
    """
    base_dir = os.path.dirname(__file__)
    env_dir = os.path.join(base_dir, "app", "env")
    data_dir = os.path.join(base_dir, "app", "data")
    env_backup_dir = get_backup_dir(hass)
    data_backup_dir = get_data_backup_dir(hass)

    total = 0

    # --- env/ sichern ---
    if os.path.exists(env_dir):
        try:
            for filename in os.listdir(env_backup_dir):
                if filename == ".gitkeep":
                    continue
                filepath = os.path.join(env_backup_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)

            for filename in os.listdir(env_dir):
                if filename == ".gitkeep":
                    continue
                src = os.path.join(env_dir, filename)
                if (
                    os.path.isfile(src)
                    and filename.endswith(".env")
                    and os.path.getsize(src) > 0
                ):
                    shutil.copy2(src, os.path.join(env_backup_dir, filename))
                    total += 1
        except OSError as err:
            _LOGGER.error("Fehler beim env-Backup: %s", err)

    # --- data/ sichern ---
    if os.path.exists(data_dir):
        try:
            for filename in os.listdir(data_backup_dir):
                filepath = os.path.join(data_backup_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)

            for filename in os.listdir(data_dir):
                src = os.path.join(data_dir, filename)
                if (
                    os.path.isfile(src)
                    and filename.endswith(".json")
                    and os.path.getsize(src) > 0
                ):
                    shutil.copy2(src, os.path.join(data_backup_dir, filename))
                    total += 1
        except OSError as err:
            _LOGGER.error("Fehler beim data-Backup: %s", err)

    if total > 0:
        _LOGGER.debug("Backup erstellt: %d Dateien (env + data)", total)
    return total > 0

