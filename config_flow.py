"""Config Flow für die iona-ha Integration.

Ermöglicht die Konfiguration über die Home Assistant UI:
- iONA Box IP-Adresse
- Benutzername & Passwort
- mein Strom Vision aktivieren/deaktivieren
"""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_IONA_BOX,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VISION_TARIFF,
    CONF_VISION_TOOLS,
    CONF_INTERVAL_LAN,
    CONF_INTERVAL_WEB,
    INTERVAL_LAN_DATA,
    INTERVAL_WEB_DATA,
)
from .data_manager import describe_meter_standoff
from .env_utils import (
    read_env_file,
    write_env_file,
    ACCOUNT_ENV,
    SECRETS_ENV,
)

# Vision-Häkchen nur anzeigen wenn die Module verfügbar sind
try:
    from .app import get_spot_prices as _  # noqa: F401
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False


class IonaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow für iona-ha."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Erster Schritt: Zugangsdaten eingeben."""
        errors = {}

        await self.async_set_unique_id("iona_integration")
        self._abort_if_unique_id_configured()

        if user_input is not None:
            # Zugangsdaten in .env Dateien schreiben
            # account.env: bestehende Werte beibehalten, vision_tariff aktualisieren
            account_data = await self.hass.async_add_executor_job(
                read_env_file, ACCOUNT_ENV
            )
            account_data[CONF_VISION_TARIFF] = str(
                user_input.get(CONF_VISION_TARIFF, False)
            )
            account_data[CONF_VISION_TOOLS] = str(
                user_input.get(CONF_VISION_TOOLS, False)
            )
            await self.hass.async_add_executor_job(
                write_env_file, ACCOUNT_ENV, account_data
            )
            # Nur IONA_BOX in secrets-n2g.env – Credentials bleiben im ConfigEntry
            await self.hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {CONF_IONA_BOX: user_input[CONF_IONA_BOX]},
            )
            return self.async_create_entry(
                title="iona-ha", data=user_input
            )

        # Bestehende Werte als Defaults laden
        n2g_env = await self.hass.async_add_executor_job(read_env_file, SECRETS_ENV)
        account_env = await self.hass.async_add_executor_job(read_env_file, ACCOUNT_ENV)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_IONA_BOX,
                    default=n2g_env.get(CONF_IONA_BOX, ""),
                ): str,
                vol.Required(
                    CONF_USERNAME,
                    default=n2g_env.get(CONF_USERNAME, ""),
                ): str,
                vol.Required(
                    CONF_PASSWORD,
                    default=n2g_env.get(CONF_PASSWORD, ""),
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                **(
                    {
                        vol.Required(
                            CONF_VISION_TARIFF,
                            default=account_env.get(CONF_VISION_TARIFF, "False").lower() == "true",
                        ): bool,
                        vol.Required(
                            CONF_VISION_TOOLS,
                            default=account_env.get(CONF_VISION_TOOLS, "False").lower() == "true",
                        ): bool,
                    }
                    if _VISION_AVAILABLE
                    else {}
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Options Flow Handler für Rekonfiguration."""
        return IonaOptionsFlowHandler()


class IonaOptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow für iona-ha (Rekonfiguration)."""

    def _manager(self):
        return self.hass.data.get(DOMAIN, {}).get("manager")

    async def async_step_init(self, user_input=None):
        """Einstieg: Formular, bei blockiertem Zählerstand vorher ein Menü.

        Ohne Fehler sieht der Dialog aus wie vor 2.3.5. Die Übernahme
        erscheint nur, solange die Meldung "Zählerstand blockiert" aktiv ist.
        """
        manager = self._manager()
        if manager is not None and manager.meter_standoff():
            return self.async_show_menu(
                step_id="init", menu_options=["settings", "accept_meter"]
            )
        return await self.async_step_settings(user_input)

    async def async_step_accept_meter(self, user_input=None):
        """Gesunkene Zählerstände nach Bestätigung übernehmen.

        Endet mit einem Abort statt `async_create_entry`: Es werden keine
        Optionen gespeichert, die Integration lädt also nicht neu.
        """
        manager = self._manager()
        rejected = manager.meter_standoff() if manager is not None else {}
        if not rejected:
            return self.async_abort(reason="meter_nothing_to_accept")

        if user_input is None:
            return self.async_show_form(
                step_id="accept_meter",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "details": describe_meter_standoff(rejected)
                },
            )

        accepted = await manager.async_accept_meter_decrease()
        if accepted is None:
            return self.async_abort(reason="meter_accept_failed")
        if not accepted:
            return self.async_abort(reason="meter_nothing_to_accept")
        return self.async_abort(
            reason="meter_accepted",
            description_placeholders={"keys": ", ".join(accepted)},
        )

    async def async_step_settings(self, user_input=None):
        """Options-Formular anzeigen."""
        if user_input is not None:
            # account.env: bestehende Werte beibehalten, vision_tariff aktualisieren
            account_data = await self.hass.async_add_executor_job(
                read_env_file, ACCOUNT_ENV
            )
            account_data[CONF_VISION_TARIFF] = str(
                user_input.get(CONF_VISION_TARIFF, False)
            )
            account_data[CONF_VISION_TOOLS] = str(
                user_input.get(CONF_VISION_TOOLS, False)
            )
            await self.hass.async_add_executor_job(
                write_env_file, ACCOUNT_ENV, account_data
            )
            # Nur IONA_BOX in secrets-n2g.env – Credentials bleiben im ConfigEntry
            await self.hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {CONF_IONA_BOX: user_input[CONF_IONA_BOX]},
            )
            # Credentials auch im ConfigEntry aktualisieren
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input
            )
            return self.async_create_entry(title="", data=user_input)

        n2g_env = await self.hass.async_add_executor_job(read_env_file, SECRETS_ENV)
        account_env = await self.hass.async_add_executor_job(read_env_file, ACCOUNT_ENV)

        # Aktuelle Werte aus ConfigEntry (dort liegen Credentials seit v2.0.5)
        entry_data = self.config_entry.data
        current_lan = entry_data.get(CONF_INTERVAL_LAN, INTERVAL_LAN_DATA)
        current_web = entry_data.get(CONF_INTERVAL_WEB, INTERVAL_WEB_DATA)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IONA_BOX, default=n2g_env.get(CONF_IONA_BOX, "")): str,
                vol.Required(CONF_USERNAME, default=entry_data.get(CONF_USERNAME, "")): str,
                vol.Required(
                    CONF_PASSWORD, default=entry_data.get(CONF_PASSWORD, "")
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                **(
                    {
                        vol.Required(
                            CONF_VISION_TARIFF,
                            default=account_env.get(CONF_VISION_TARIFF, "False").lower() == "true",
                        ): bool,
                        vol.Required(
                            CONF_VISION_TOOLS,
                            default=account_env.get(CONF_VISION_TOOLS, "False").lower() == "true",
                        ): bool,
                    }
                    if _VISION_AVAILABLE
                    else {}
                ),
                vol.Required(
                    CONF_INTERVAL_LAN,
                    default=current_lan,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=60, step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    CONF_INTERVAL_WEB,
                    default=current_web,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=10, max=3600, step=10,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=data_schema)
