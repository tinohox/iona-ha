"""Die iona-ha Integration für Home Assistant.

Stellt Energiedaten des iONA-Systems (enviaM) in Home Assistant bereit.
Nutzt ausschließlich HA-native async Patterns (kein subprocess, kein threading).
"""

import logging
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
from homeassistant.components.http import StaticPathConfig
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
    LOVELACE_CARD_URL,
    LOVELACE_VISION_CARD_URL,
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

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the iona component (YAML – nicht verwendet, nur Platzhalter)."""
    import os
    hass.data.setdefault(DOMAIN, {})

    # HTTP-Pfad für Custom Card einmalig registrieren
    if not hass.data[DOMAIN].get("_cards_registered"):
        card_file = os.path.join(os.path.dirname(__file__), "www", "iona-card.js")
        vision_card_file = os.path.join(os.path.dirname(__file__), "www", "iona-vision-card.js")
        paths = []
        if os.path.isfile(card_file):
            paths.append(StaticPathConfig("/iona_cards/iona-card.js", card_file, False))
        if os.path.isfile(vision_card_file):
            paths.append(StaticPathConfig("/iona_cards/iona-vision-card.js", vision_card_file, False))
        if paths:
            await hass.http.async_register_static_paths(paths)
            hass.data[DOMAIN]["_cards_registered"] = True
            _LOGGER.debug("iona: Custom Card HTTP-Pfade registriert")

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

    # 7. Lovelace-Ressourcen für Custom Cards automatisch eintragen
    await _async_ensure_lovelace_resource(hass, entry, LOVELACE_CARD_URL)
    await _async_ensure_lovelace_resource(hass, entry, LOVELACE_VISION_CARD_URL)

    _LOGGER.info("iona-ha Integration erfolgreich eingerichtet")
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload der Integration bei Options-Änderung."""
    _LOGGER.info("Options geändert – Integration wird neu geladen")
    await hass.config_entries.async_reload(entry.entry_id)


async def _sync_credentials(
    hass: HomeAssistant, entry: ConfigEntry, *, restored: bool = False
) -> None:
    """Synchronisiert Einstellungen zwischen ConfigEntry und .env Dateien.

    secrets-n2g.env enthält nur noch IONA_BOX (keine Credentials).
    Credentials bleiben ausschließlich im HA ConfigEntry (verschlüsselt).

    Migration: Wenn secrets-n2g.env noch USERNAME/PASSWORD enthält (Update
    von älterer Version), werden diese in den ConfigEntry übernommen und
    anschließend aus der env-Datei entfernt.
    """
    # --- secrets-n2g.env ---
    secrets_exists = await hass.async_add_executor_job(env_file_exists, SECRETS_ENV)
    entry_box = entry.data.get(CONF_IONA_BOX, "")

    if secrets_exists:
        secrets_data = await hass.async_add_executor_job(read_env_file, SECRETS_ENV)

        # Migration: Credentials aus alter env-Datei in ConfigEntry übernehmen
        env_user = secrets_data.get(CONF_USERNAME, "")
        env_pass = secrets_data.get(CONF_PASSWORD, "")
        if env_user and env_pass:
            entry_user = entry.data.get(CONF_USERNAME, "")
            entry_pass = entry.data.get(CONF_PASSWORD, "")
            if env_user != entry_user or env_pass != entry_pass:
                new_data = dict(entry.data)
                new_data[CONF_USERNAME] = env_user
                new_data[CONF_PASSWORD] = env_pass
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info(
                    "Migration: Credentials aus secrets-n2g.env in ConfigEntry übernommen"
                )

            # env-Datei bereinigen: nur noch IONA_BOX behalten
            env_box = secrets_data.get(CONF_IONA_BOX, entry_box)
            await hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {CONF_IONA_BOX: env_box},
            )
            _LOGGER.info(
                "Migration: USERNAME/PASSWORD aus secrets-n2g.env entfernt"
            )
        elif restored and entry_box:
            # Nach Backup-Restore: ConfigEntry hat Vorrang
            await hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {CONF_IONA_BOX: entry_box},
            )
            _LOGGER.info(
                "secrets-n2g.env aus ConfigEntry aktualisiert nach Restore (IP: %s)",
                entry_box,
            )
        elif not restored:
            # env war schon da → IONA_BOX in ConfigEntry aktualisieren falls abweichend
            env_box = secrets_data.get(CONF_IONA_BOX, "")
            if env_box and env_box != entry_box:
                new_data = dict(entry.data)
                new_data[CONF_IONA_BOX] = env_box
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info(
                    "ConfigEntry IONA_BOX aus secrets-n2g.env aktualisiert (IP: %s)",
                    env_box,
                )
    elif not secrets_exists and entry_box:
        # env fehlt → IONA_BOX aus ConfigEntry wiederherstellen
        await hass.async_add_executor_job(
            write_env_file,
            SECRETS_ENV,
            {CONF_IONA_BOX: entry_box},
        )
        _LOGGER.info("IONA_BOX aus ConfigEntry wiederhergestellt")

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


async def _async_ensure_lovelace_resource(
    hass: HomeAssistant, entry: ConfigEntry, url: str
) -> None:
    """Trägt die Custom Card als Lovelace-Ressource ein, falls noch nicht vorhanden.

    Nutzt die interne HA Lovelace Storage-API. Falls diese nicht verfügbar ist,
    wird eine persistente Benachrichtigung mit manueller Anleitung angezeigt
    (einmalig pro Entry).
    """
    try:
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            raise AttributeError("lovelace nicht in hass.data")

        resources = getattr(lovelace, "resources", None)
        if resources is None:
            raise AttributeError("lovelace.resources nicht verfügbar")

        await resources.async_load()
        existing = [r["url"] for r in resources.async_items()]
        if url not in existing:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.info("iona: Lovelace-Ressource eingetragen: %s", url)
        else:
            _LOGGER.debug("iona: Lovelace-Ressource bereits vorhanden: %s", url)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("iona: Lovelace-API nicht verfügbar (%s) – zeige Hinweis", exc)
        notif_key = f"{DOMAIN}_card_hint_{entry.entry_id}"
        if not hass.data[DOMAIN].get(notif_key):
            hass.data[DOMAIN][notif_key] = True
            hass.components.persistent_notification.async_create(
                title="iONA – Custom Card einrichten",
                message=(
                    "Die iONA Lovelace Card konnte nicht automatisch registriert werden.\n\n"
                    "Bitte manuell eintragen:\n"
                    "**Einstellungen → Dashboards → Ressourcen → Hinzufügen**\n\n"
                    f"URL: `{url}`  |  Typ: JavaScript-Modul"
                ),
                notification_id=notif_key,
            )


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
