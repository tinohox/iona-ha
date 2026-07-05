"""Button-Entity für manuelle Vision-Neuberechnung."""

import logging

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN
from .env_utils import is_vision_tools_enabled

_LOGGER = logging.getLogger(__name__)

try:
    from .app import get_spot_prices as _  # noqa: F401
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False


async def async_setup_entry(hass, entry, async_add_entities):
    """Richte die Button-Plattform ein."""
    if not _VISION_AVAILABLE:
        return

    tools_enabled = await hass.async_add_executor_job(is_vision_tools_enabled)
    if tools_enabled:
        async_add_entities([IonaVisionBerechnungButton(hass)], update_before_add=False)


class IonaVisionBerechnungButton(ButtonEntity):
    """Button zum manuellen Auslösen der Vision-Neuberechnung."""

    _attr_has_entity_name = True

    def __init__(self, hass):
        self._hass = hass

    @property
    def name(self) -> str:
        return "Vision Tools – Berechnen"

    @property
    def unique_id(self) -> str:
        return "iona_vision_berechnen"

    @property
    def icon(self) -> str:
        return "mdi:calculator-variant"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {("iona", "vision_tools")},
            "name": "mein Strom Vision Tools",
            "manufacturer": "enviaM",
            "model": "Vision Optimierung",
        }

    async def async_press(self) -> None:
        """Manuelle Vision-Neuberechnung erzwingen."""
        manager = self._hass.data.get(DOMAIN, {}).get("manager")
        if manager is not None:
            try:
                await manager._task_vision_force()
                _LOGGER.info("Vision: Manuelle Neuberechnung ausgelöst")
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Vision: Manuelle Neuberechnung fehlgeschlagen")
