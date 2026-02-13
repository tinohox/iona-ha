"""Switch-Entity für iona-ha (Nacht-Modus Toggle)."""

import logging

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .env_utils import get_nur_nacht, set_nur_nacht, is_vision_tools_enabled

_LOGGER = logging.getLogger(__name__)

# Vision nur verfügbar wenn Module vorhanden
try:
    from .app import get_spot_prices as _  # noqa: F401
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False


async def async_setup_entry(hass, entry, async_add_entities):
    """Richte die Switch-Plattform ein."""
    if not _VISION_AVAILABLE:
        return

    tools_enabled = await hass.async_add_executor_job(is_vision_tools_enabled)

    if tools_enabled:
        async_add_entities([IonaNachtModusSwitch(hass)], update_before_add=True)


class IonaNachtModusSwitch(SwitchEntity):
    """Switch für den Nacht-Modus (nur Nachtzeiten durchsuchen)."""

    _attr_has_entity_name = True

    def __init__(self, hass):
        self._hass = hass
        self._attr_is_on = False

    @property
    def name(self) -> str:
        return "Vision Tools – nur Nachtstrom"

    @property
    def unique_id(self) -> str:
        return "iona_vision_nur_nacht"

    @property
    def icon(self) -> str:
        return "mdi:weather-night" if self.is_on else "mdi:white-balance-sunny"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {("iona", "vision_tools")},
            "name": "mein Strom Vision Tools",
            "manufacturer": "enviaM",
            "model": "Vision Optimierung",
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Nacht-Modus aktivieren."""
        await self._hass.async_add_executor_job(set_nur_nacht, True)
        self._attr_is_on = True

        manager = self._hass.data.get(DOMAIN, {}).get("manager")
        if manager is not None:
            try:
                await manager._task_vision()
                _LOGGER.debug("Vision-Neuberechnung: Nacht-Modus AN")
            except Exception:
                _LOGGER.warning("Vision-Neuberechnung nach Nacht-Modus fehlgeschlagen")

    async def async_turn_off(self, **kwargs) -> None:
        """Nacht-Modus deaktivieren."""
        await self._hass.async_add_executor_job(set_nur_nacht, False)
        self._attr_is_on = False

        manager = self._hass.data.get(DOMAIN, {}).get("manager")
        if manager is not None:
            try:
                await manager._task_vision()
                _LOGGER.debug("Vision-Neuberechnung: Nacht-Modus AUS")
            except Exception:
                _LOGGER.warning("Vision-Neuberechnung nach Nacht-Modus fehlgeschlagen")

    async def async_update(self) -> None:
        """Aktualisiere den Wert aus der Datei."""
        self._attr_is_on = await self._hass.async_add_executor_job(get_nur_nacht)
