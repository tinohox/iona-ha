"""Backup-Modul für .env Dateien.

Verwaltet regelmäßige Backups des env/ Verzeichnisses.
Backups werden im Home Assistant .storage Verzeichnis gespeichert,
das von HACS-Updates nicht betroffen ist.
"""

import os
import json
import shutil
import logging

_LOGGER = logging.getLogger(__name__)

# Dateien, die eine Plausibilitätsprüfung durchlaufen, bevor sie ein
# vorhandenes Backup überschreiben dürfen. meter_db.json trägt den
# Zählerstand: geht er verloren, fehlt value_allows_update() der
# Vergleichswert, und Home Assistant bucht den nächsten Wert bei
# state_class total_increasing komplett als Verbrauch.
_GUARDED_DATA_FILES = ("meter_db.json",)


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

    # Pro fehlender Datei wiederherstellen, nicht alles-oder-nichts.
    # Die alte Regel "nur wenn data/ komplett leer ist" griff praktisch nie:
    # spotpreise_db.json & Co. sind nach dem ersten Abruf sofort wieder da,
    # und meter_db.json – die einzige Datei mit unersetzbarem Inhalt – blieb
    # dann auf der Strecke.
    if os.path.exists(data_backup_dir):
        try:
            for filename in os.listdir(data_backup_dir):
                if not filename.endswith(".json"):
                    continue
                src = os.path.join(data_backup_dir, filename)
                dst = os.path.join(data_dir, filename)
                if not os.path.isfile(src) or os.path.exists(dst):
                    continue
                shutil.copy2(src, dst)
                _LOGGER.info("data/%s aus Backup wiederhergestellt", filename)
                restored = True
        except OSError as err:
            _LOGGER.error("Fehler beim Wiederherstellen von data/: %s", err)

    return restored


def _is_plausible(path: str, filename: str) -> bool:
    """Prüft, ob eine Datendatei brauchbaren Inhalt hat.

    Verhindert, dass ein frisch entstandener Rumpf-Datensatz ein
    vollständiges Backup überschreibt (z. B. direkt nach einem HACS-Update).
    """
    if filename != "meter_db.json":
        return True
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        entries = list(data.get("_default", {}).values())
    except (OSError, ValueError, AttributeError):
        return False
    return any(
        isinstance(e, dict)
        and e.get("device_id") == "Stromzaehler"
        and e.get("Gesamtverbrauch") is not None
        for e in entries
    )


def _copy_atomic(src: str, dst: str) -> None:
    """Kopiert über eine temporäre Datei und os.replace().

    Ohne das läge das Backup während des Kopierens unvollständig vor – genau
    das Fenster, in dem ein Neustart es unbrauchbar macht. Das .tmp-Suffix
    ist wichtig: der Restore und das Backup filtern auf .json.
    """
    tmp = dst + ".tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


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
    # Wie beim data-Backup unten: kein vorheriges Leeren. Nach einem
    # HACS-Update ist app/env/ gelöscht, Home Assistant läuft aber bis zum
    # Neustart weiter – ein Backup-Lauf in diesem Fenster hätte die gesicherten
    # Zugangsdaten und Tokens mitgenommen.
    if os.path.exists(env_dir):
        try:
            for filename in os.listdir(env_dir):
                if filename == ".gitkeep":
                    continue
                src = os.path.join(env_dir, filename)
                if (
                    not os.path.isfile(src)
                    or not filename.endswith(".env")
                    or os.path.getsize(src) == 0
                ):
                    continue
                _copy_atomic(src, os.path.join(env_backup_dir, filename))
                total += 1
        except OSError as err:
            _LOGGER.error("Fehler beim env-Backup: %s", err)

    # --- data/ sichern ---
    # Bewusst OHNE vorheriges Leeren des Backup-Verzeichnisses: Ein
    # HACS-Update löscht app/data/, Home Assistant läuft aber weiter. Das
    # nächste stündliche Backup hätte sonst das noch gute Backup durch den
    # frisch entstandenen, unvollständigen Stand ersetzt – und der Restore
    # beim nächsten Start hätte nichts Brauchbares mehr gefunden.
    # Ein Backup wird nur überschrieben, nie gelöscht.
    if os.path.exists(data_dir):
        try:
            for filename in os.listdir(data_dir):
                src = os.path.join(data_dir, filename)
                if (
                    not os.path.isfile(src)
                    or not filename.endswith(".json")
                    or os.path.getsize(src) == 0
                ):
                    continue
                if filename in _GUARDED_DATA_FILES and not _is_plausible(src, filename):
                    _LOGGER.warning(
                        "data/%s wirkt unvollständig – vorhandenes Backup "
                        "bleibt unangetastet",
                        filename,
                    )
                    continue
                _copy_atomic(src, os.path.join(data_backup_dir, filename))
                total += 1
        except OSError as err:
            _LOGGER.error("Fehler beim data-Backup: %s", err)

    if total > 0:
        _LOGGER.debug("Backup erstellt: %d Dateien (env + data)", total)
    return total > 0

