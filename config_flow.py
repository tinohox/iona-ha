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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN, CONF_IONA_BOX, CONF_USERNAME, CONF_PASSWORD, CONF_VISION_TARIFF, CONF_VISION_TOOLS
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
            await self.hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {
                    CONF_IONA_BOX: user_input[CONF_IONA_BOX],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                },
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

    async def async_step_init(self, user_input=None):
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
            await self.hass.async_add_executor_job(
                write_env_file,
                SECRETS_ENV,
                {
                    CONF_IONA_BOX: user_input[CONF_IONA_BOX],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                },
            )
            # Credentials auch im ConfigEntry aktualisieren
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input
            )
            return self.async_create_entry(title="", data=user_input)

        n2g_env = await self.hass.async_add_executor_job(read_env_file, SECRETS_ENV)
        account_env = await self.hass.async_add_executor_job(read_env_file, ACCOUNT_ENV)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IONA_BOX, default=n2g_env.get(CONF_IONA_BOX, "")): str,
                vol.Required(CONF_USERNAME, default=n2g_env.get(CONF_USERNAME, "")): str,
                vol.Required(
                    CONF_PASSWORD, default=n2g_env.get(CONF_PASSWORD, "")
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
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
