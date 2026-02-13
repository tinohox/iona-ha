"""Number-Entity für konfigurierbare Werte (Stunden-Block für Vision)."""

from homeassistant.components.number import NumberEntity, NumberMode

from .env_utils import get_stunden_block, set_stunden_block, is_vision_enabled


async def async_setup_entry(hass, entry, async_add_entities):
    """Richte die Number-Plattform ein."""
    vision_enabled = await hass.async_add_executor_job(is_vision_enabled)

    if vision_enabled:
        async_add_entities([IonaStundenBlockNumber(hass)], update_before_add=True)


class IonaStundenBlockNumber(NumberEntity):
    """Number-Entity für den Stunden-Block (1-8h)."""

    _attr_has_entity_name = True

    def __init__(self, hass):
        self._hass = hass
        self._attr_native_value = 2

    @property
    def name(self) -> str:
        return "mein Strom Vision – Zeitraum"

    @property
    def unique_id(self) -> str:
        return "iona_vision_stunden_block"

    @property
    def native_min_value(self) -> float:
        return 1

    @property
    def native_max_value(self) -> float:
        return 8

    @property
    def native_step(self) -> float:
        return 1

    @property
    def native_unit_of_measurement(self) -> str:
        return "h"

    @property
    def mode(self) -> NumberMode:
        return NumberMode.SLIDER

    @property
    def icon(self) -> str:
        return "mdi:clock-time-four-outline"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {("iona", "vision_strom")},
            "name": "mein Strom Vision",
            "manufacturer": "enviaM",
            "model": "Vision Sensor",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Setze den neuen Wert."""
        int_value = int(value)
        await self._hass.async_add_executor_job(set_stunden_block, int_value)
        self._attr_native_value = int_value

    async def async_update(self) -> None:
        """Aktualisiere den Wert aus der Datei."""
        self._attr_native_value = await self._hass.async_add_executor_job(
            get_stunden_block
        )

