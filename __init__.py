"""Die iona-ha Integration für Home Assistant.

Stellt Energiedaten des iONA-Systems (enviaM) in Home Assistant bereit.
Nutzt ausschließlich HA-native async Patterns (kein subprocess, kein threading).
"""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PLATFORMS
from .env_backup import restore_env_from_backup, backup_env_files
from .env_utils import migrate_env_files

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the iona component (YAML – nicht verwendet, nur Platzhalter)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richte die iona-ha Integration ein (Config Entry)."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Migration: accound.env → account.env (Tippfehler v1.x)
    await hass.async_add_executor_job(migrate_env_files)

    # 2. Env-Dateien aus Backup wiederherstellen falls durch HACS-Update gelöscht
    await hass.async_add_executor_job(restore_env_from_backup, hass)

    # 3. Datenmanager starten (ersetzt subprocess + main.py)
    from .data_manager import IonaDataManager

    manager = IonaDataManager(hass)
    hass.data[DOMAIN]["manager"] = manager
    await manager.async_start()

    # 4. Plattformen laden (sensor, number)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. Stündliches Backup der env-Dateien
    async def _periodic_backup(_now=None):
        await hass.async_add_executor_job(backup_env_files, hass)

    entry.async_on_unload(
        async_track_time_interval(hass, _periodic_backup, timedelta(hours=1))
    )

    _LOGGER.info("iona-ha Integration erfolgreich eingerichtet")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlade die iona-ha Integration sauber."""
    # Plattformen entladen
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Datenmanager stoppen (periodische Tasks beenden)
        manager = hass.data[DOMAIN].pop("manager", None)
        if manager is not None:
            await manager.async_stop()

        # Letztes Backup vor dem Entladen
        await hass.async_add_executor_job(backup_env_files, hass)

        _LOGGER.info("iona-ha Integration entladen")

    return unload_ok
