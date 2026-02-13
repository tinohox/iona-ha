"""Number-Entity für konfigurierbare Werte (Stunden-Block für Vision)."""

import logging

from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .env_utils import (
    get_stunden_block,
    set_stunden_block,
    get_vorausschau_stunden,
    set_vorausschau_stunden,
    get_max_datenlage_stunden,
    is_vision_tools_enabled,
)

_LOGGER = logging.getLogger(__name__)

# Vision nur verfügbar wenn Module vorhanden
try:
    from .app import get_spot_prices as _  # noqa: F401
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False


async def async_setup_entry(hass, entry, async_add_entities):
    """Richte die Number-Plattform ein."""
    if not _VISION_AVAILABLE:
        return

    tools_enabled = await hass.async_add_executor_job(is_vision_tools_enabled)

    if tools_enabled:
        async_add_entities(
            [IonaStundenBlockNumber(hass), IonaVorausschauNumber(hass)],
            update_before_add=True,
        )


class IonaStundenBlockNumber(NumberEntity):
    """Number-Entity für den Stunden-Block (dynamisch bis Datenlage-1)."""

    _attr_has_entity_name = True

    def __init__(self, hass):
        self._hass = hass
        self._attr_native_value = 2
        self._cached_max_datenlage = 48  # wird in async_update aktualisiert

    @property
    def name(self) -> str:
        return "Vision Tools – Zeitraum"

    @property
    def unique_id(self) -> str:
        return "iona_vision_stunden_block"

    @property
    def native_min_value(self) -> float:
        return 1

    @property
    def native_max_value(self) -> float:
        # Zeitraum darf maximal Datenlage - 1 sein (1h für Vorausschau)
        return max(1, self._cached_max_datenlage - 1)

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
            "identifiers": {("iona", "vision_tools")},
            "name": "mein Strom Vision Tools",
            "manufacturer": "enviaM",
            "model": "Vision Optimierung",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Setze den neuen Wert und passe Vorausschau an falls nötig."""
        int_value = int(value)
        await self._hass.async_add_executor_job(set_stunden_block, int_value)
        self._attr_native_value = int_value

        # Vorausschau muss immer > Zeitraum sein → ggf. anheben
        vorausschau = await self._hass.async_add_executor_job(get_vorausschau_stunden)
        if vorausschau <= int_value:
            new_vorausschau = int_value + 1
            await self._hass.async_add_executor_job(
                set_vorausschau_stunden, new_vorausschau
            )
            _LOGGER.info(
                "Vorausschau automatisch auf %dh angehoben (Zeitraum=%dh)",
                new_vorausschau, int_value,
            )

        # Vision sofort neu berechnen statt auf nächsten 5-Min-Zyklus zu warten
        manager = self._hass.data.get(DOMAIN, {}).get("manager")
        if manager is not None:
            try:
                await manager._task_vision()
                _LOGGER.debug("Vision-Neuberechnung nach Regler-Änderung auf %dh", int_value)
            except Exception:
                _LOGGER.warning("Vision-Neuberechnung nach Regler-Änderung fehlgeschlagen")

    async def async_update(self) -> None:
        """Aktualisiere den Wert und die Datenlage."""
        self._attr_native_value = await self._hass.async_add_executor_job(
            get_stunden_block
        )
        self._cached_max_datenlage = await self._hass.async_add_executor_job(
            get_max_datenlage_stunden
        )


class IonaVorausschauNumber(NumberEntity):
    """Number-Entity für die Vorausschau (Zeitraum+1 bis Datenlage)."""

    _attr_has_entity_name = True

    def __init__(self, hass):
        self._hass = hass
        self._attr_native_value = 12
        self._cached_zeitraum = 2  # Cache für dynamisches Minimum
        self._cached_max_datenlage = 48  # wird in async_update aktualisiert

    @property
    def name(self) -> str:
        return "Vision Tools – Vorausschau"

    @property
    def unique_id(self) -> str:
        return "iona_vision_vorausschau"

    @property
    def native_min_value(self) -> float:
        return self._cached_zeitraum + 1

    @property
    def native_max_value(self) -> float:
        return max(self._cached_zeitraum + 1, self._cached_max_datenlage)

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
        return "mdi:binoculars"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {("iona", "vision_tools")},
            "name": "mein Strom Vision Tools",
            "manufacturer": "enviaM",
            "model": "Vision Optimierung",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Setze den neuen Wert (muss > Zeitraum sein)."""
        int_value = int(value)
        zeitraum = await self._hass.async_add_executor_job(get_stunden_block)
        min_vorausschau = zeitraum + 1

        # Erzwinge Minimum
        if int_value < min_vorausschau:
            int_value = min_vorausschau
            _LOGGER.info(
                "Vorausschau auf Minimum %dh korrigiert (Zeitraum=%dh)",
                int_value, zeitraum,
            )

        await self._hass.async_add_executor_job(set_vorausschau_stunden, int_value)
        self._attr_native_value = int_value
        self._cached_zeitraum = zeitraum

        # Vision sofort neu berechnen
        manager = self._hass.data.get(DOMAIN, {}).get("manager")
        if manager is not None:
            try:
                await manager._task_vision()
                _LOGGER.debug("Vision-Neuberechnung nach Vorausschau-Änderung auf %dh", int_value)
            except Exception:
                _LOGGER.warning("Vision-Neuberechnung nach Vorausschau-Änderung fehlgeschlagen")

    async def async_update(self) -> None:
        """Aktualisiere den Wert, Zeitraum-Cache und Datenlage."""
        self._attr_native_value = await self._hass.async_add_executor_job(
            get_vorausschau_stunden
        )
        self._cached_zeitraum = await self._hass.async_add_executor_job(
            get_stunden_block
        )
        self._cached_max_datenlage = await self._hass.async_add_executor_job(
            get_max_datenlage_stunden
        )

