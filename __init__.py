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
    read_env_file,
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
    restored = await hass.async_add_executor_job(restore_env_from_backup, hass)

    # 2b. Credentials synchronisieren (env ↔ ConfigEntry)
    #     Nach Restore: ConfigEntry hat Vorrang (Backup kann veraltet sein)
    #     Ohne Restore: env hat Vorrang (manuelle Änderungen übernehmen)
    await _sync_credentials(hass, entry, restored=restored)

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

    # 6. Bei Options-Änderung Integration neu laden
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info("iona-ha Integration erfolgreich eingerichtet")
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload der Integration bei Options-Änderung."""
    _LOGGER.info("Options geändert – Integration wird neu geladen")
    await hass.config_entries.async_reload(entry.entry_id)


async def _sync_credentials(
    hass: HomeAssistant, entry: ConfigEntry, *, restored: bool = False
) -> None:
    """Synchronisiert Zugangsdaten zwischen ConfigEntry und .env Dateien.

    - restored=True  → env wurde gerade aus Backup wiederhergestellt,
                        ConfigEntry hat Vorrang (Backup kann veraltet sein)
    - restored=False → env war schon vorhanden (manuell bearbeitet),
                        env hat Vorrang über ConfigEntry
    - env fehlt      → aus ConfigEntry wiederherstellen (z.B. nach HACS-Update)
    """
    # --- secrets-n2g.env ---
    secrets_exists = await hass.async_add_executor_job(env_file_exists, SECRETS_ENV)
    entry_box = entry.data.get(CONF_IONA_BOX, "")
    entry_user = entry.data.get(CONF_USERNAME, "")
    entry_pass = entry.data.get(CONF_PASSWORD, "")

    if secrets_exists and restored and entry_box and entry_user and entry_pass:
        # Nach Backup-Restore: ConfigEntry ist die aktuelle Wahrheit
        await hass.async_add_executor_job(
            write_env_file,
            SECRETS_ENV,
            {
                CONF_IONA_BOX: entry_box,
                CONF_USERNAME: entry_user,
                CONF_PASSWORD: entry_pass,
            },
        )
        _LOGGER.info(
            "secrets-n2g.env aus ConfigEntry aktualisiert nach Restore (IP: %s)",
            entry_box,
        )
    elif secrets_exists and not restored:
        # env war schon da → ConfigEntry aktualisieren falls abweichend
        secrets_data = await hass.async_add_executor_job(read_env_file, SECRETS_ENV)
        env_box = secrets_data.get(CONF_IONA_BOX, "")
        env_user = secrets_data.get(CONF_USERNAME, "")
        env_pass = secrets_data.get(CONF_PASSWORD, "")
        if (
            env_box and env_user and env_pass
            and (
                env_box != entry_box
                or env_user != entry_user
                or env_pass != entry_pass
            )
        ):
            new_data = dict(entry.data)
            new_data[CONF_IONA_BOX] = env_box
            new_data[CONF_USERNAME] = env_user
            new_data[CONF_PASSWORD] = env_pass
            hass.config_entries.async_update_entry(entry, data=new_data)
            _LOGGER.info("ConfigEntry aus secrets-n2g.env aktualisiert (IP: %s)", env_box)
    elif not secrets_exists and entry_box and entry_user and entry_pass:
        # env fehlt → aus ConfigEntry wiederherstellen
        await hass.async_add_executor_job(
            write_env_file,
            SECRETS_ENV,
            {
                CONF_IONA_BOX: entry_box,
                CONF_USERNAME: entry_user,
                CONF_PASSWORD: entry_pass,
            },
        )
        _LOGGER.info("Zugangsdaten aus ConfigEntry wiederhergestellt")

    # --- account.env ---
    account_exists = await hass.async_add_executor_job(env_file_exists, ACCOUNT_ENV)
    if account_exists and not restored:
        # env war schon da → ConfigEntry aktualisieren falls abweichend
        account_data = await hass.async_add_executor_job(read_env_file, ACCOUNT_ENV)
        env_vision = account_data.get(CONF_VISION_TARIFF, "False").lower() == "true"
        env_tools = account_data.get(CONF_VISION_TOOLS, "False").lower() == "true"
        entry_vision = entry.data.get(CONF_VISION_TARIFF, False)
        entry_tools = entry.data.get(CONF_VISION_TOOLS, False)
        if env_vision != entry_vision or env_tools != entry_tools:
            new_data = dict(entry.data)
            new_data[CONF_VISION_TARIFF] = env_vision
            new_data[CONF_VISION_TOOLS] = env_tools
            hass.config_entries.async_update_entry(entry, data=new_data)
            _LOGGER.info("ConfigEntry aus account.env aktualisiert")
    elif not account_exists and entry.data:
        # env fehlt → aus ConfigEntry wiederherstellen
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
