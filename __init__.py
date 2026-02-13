"""Die iona-ha Integration für Home Assistant.

Stellt Energiedaten des iONA-Systems (enviaM) in Home Assistant bereit.
Nutzt ausschließlich HA-native async Patterns (kein subprocess, kein threading).
"""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_IONA_BOX,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VISION_TARIFF,
    CONF_VISION_TOOLS,
)
from .env_backup import restore_env_from_backup, backup_env_files
from .env_utils import (
    migrate_env_files,
    write_env_file,
    env_file_exists,
    ACCOUNT_ENV,
    SECRETS_ENV,
)

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

    # 2b. Credentials aus ConfigEntry wiederherstellen wenn env-Dateien fehlen
    await _restore_credentials_from_entry(hass, entry)

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


async def _restore_credentials_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Stellt Zugangsdaten aus dem ConfigEntry wieder her.

    Wenn die .env Dateien fehlen (z.B. nach HACS-Update) aber die Daten
    noch im ConfigEntry gespeichert sind, werden sie neu geschrieben.
    """
    secrets_exists = await hass.async_add_executor_job(env_file_exists, SECRETS_ENV)
    if not secrets_exists and entry.data:
        iona_box = entry.data.get(CONF_IONA_BOX)
        username = entry.data.get(CONF_USERNAME)
        password = entry.data.get(CONF_PASSWORD)
        if iona_box and username and password:
            await hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {
                    CONF_IONA_BOX: iona_box,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                },
            )
            _LOGGER.info("Zugangsdaten aus ConfigEntry wiederhergestellt")

    account_exists = await hass.async_add_executor_job(env_file_exists, ACCOUNT_ENV)
    if not account_exists and entry.data:
        vision = entry.data.get(CONF_VISION_TARIFF, False)
        tools = entry.data.get(CONF_VISION_TOOLS, False)
        await hass.async_add_executor_job(
            write_env_file,
            ACCOUNT_ENV,
            {
                CONF_VISION_TARIFF: str(vision),
                CONF_VISION_TOOLS: str(tools),
            },
        )
        _LOGGER.info("Account-Einstellungen aus ConfigEntry wiederhergestellt")


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
