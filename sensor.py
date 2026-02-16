"""Sensor-Plattform für iona-ha.

Erstellt Sensor-Entities für Stromzähler-Daten und
mein Strom Vision Preissensoren aus TinyDB JSON-Dateien.
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from logging import getLogger

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from tinydb import TinyDB

from .const import INTERVAL_SENSOR_UPDATE
from .env_utils import is_vision_enabled, is_vision_tools_enabled

# Vision nur verfügbar wenn Module vorhanden
try:
    from .app import get_spot_prices as _  # noqa: F401
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False

# Pfade relativ zur Datei
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "app", "data", "meter_db.json")
VISION_DB_PATH = os.path.join(BASE_DIR, "app", "data", "vision_db.json")

SCAN_INTERVAL = timedelta(seconds=INTERVAL_SENSOR_UPDATE)


# -------------------- Sync Reader (im Executor aufrufen) --------------------


def _read_tinydb_table(path: str) -> dict:
    """Liest TinyDB-Storage (Tabelle '_default') -> {device_id: entry}."""
    try:
        with TinyDB(path) as db:
            table = db.table("_default")
            result = {}
            for entry in table.all():
                if not isinstance(entry, dict):
                    continue
                device_id = entry.get("device_id")
                if not device_id:
                    doc_id = entry.get("doc_id", len(result) + 1)
                    device_id = str(doc_id)
                entry_copy = dict(entry)
                entry_copy["device_id"] = device_id
                result[device_id] = entry_copy
            return result
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return {}


def _read_plain_json(path: str) -> dict:
    """Liest JSON; unterstützt TinyDB-Format {'_default': {'1': {...}}}."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict) and isinstance(data.get("_default"), dict):
        result = {}
        for doc_id, entry in data["_default"].items():
            if not isinstance(entry, dict):
                continue
            device_id = entry.get("device_id") or str(doc_id)
            e = dict(entry)
            e["device_id"] = device_id
            result[device_id] = e
        return result

    if isinstance(data, list):
        result = {}
        for idx, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            device_id = entry.get("device_id") or str(idx)
            e = dict(entry)
            e["device_id"] = device_id
            result[device_id] = e
        return result

    if isinstance(data, dict):
        result = {}
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            e = dict(entry)
            e["device_id"] = e.get("device_id") or str(key)
            result[e["device_id"]] = e
        return result

    return {}


def _read_db_generic(path: str) -> dict:
    """TinyDB lesen; bei Fehlern plain JSON als Fallback."""
    try:
        return _read_tinydb_table(path)
    except Exception:
        try:
            return _read_plain_json(path)
        except Exception:
            return {}


def load_all_db_sync() -> dict:
    """Merged meter_db.json + vision_db.json."""
    merged = {}
    try:
        merged.update(_read_db_generic(DB_PATH))
    except Exception:
        pass
    try:
        merged.update(_read_db_generic(VISION_DB_PATH))
    except Exception:
        pass
    return merged


async def load_all_db(hass) -> dict:
    """Async Wrapper – File-IO in den Executor."""
    return await hass.async_add_executor_job(load_all_db_sync)


# -------------------- Entity --------------------


class IonaSensor(CoordinatorEntity, Entity):
    """Sensor-Entity für Stromzähler- und Vision-Daten."""

    ENERGY_KEYS = {"Gesamtverbrauch", "Gesamteinspeisung"}
    POWER_KEYS = {"Momentanleistung"}
    VISION_PRICE_KEYS = {
        "aktueller_preis",
    }
    VISION_TOOLS_KEYS = {
        "guenstigste_startzeit",
        "guenstigste_summe",
    }
    VISION_KEYS = VISION_PRICE_KEYS | VISION_TOOLS_KEYS

    def __init__(self, coordinator, device_id: str, sensor_key: str, attributes: dict):
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._initial_attrs = dict(attributes) if attributes else {}
        self._unit_cached = self._initial_attrs.get(f"{sensor_key}_unit")

    def _is_vision_data(self) -> bool:
        device = self.coordinator.data.get(self._device_id, {})
        return any(key in device for key in self.VISION_KEYS)

    @property
    def name(self) -> str:
        if self._is_vision_data():
            device = self.coordinator.data.get(self._device_id, {})
            stunden = device.get("stunden_block", 2)
            name_map = {
                "aktueller_preis": "Strompreis für die aktuelle 1/4h",
                "guenstigste_startzeit": f"günstigste Startzeit für {stunden}h",
                "guenstigste_summe": f"Durchschnittskosten für die {stunden}h",
            }
            if self._sensor_key in self.VISION_TOOLS_KEYS:
                return f"Vision Tools – {name_map.get(self._sensor_key, self._sensor_key)}"
            return f"Stromzähler {name_map.get(self._sensor_key, self._sensor_key)}"
        if self._sensor_key == "source":
            return "Stromzähler Datenquelle"
        return f"Stromzähler {self._sensor_key}"

    @property
    def unique_id(self) -> str:
        if self._is_vision_data():
            base = f"vision_{self._device_id}_{self._sensor_key}"
        else:
            device = self.coordinator.data.get(self._device_id, {})
            actual_id = device.get("device_id", self._device_id)
            base = f"meter_{actual_id}_{self._sensor_key}"

        suffix = hashlib.md5(base.encode()).hexdigest()[:8]
        prefix = "iona_vision" if self._is_vision_data() else "iona_meter"
        return f"{prefix}_{self._sensor_key}_{suffix}"

    @property
    def state(self):
        device = self.coordinator.data.get(self._device_id, {})
        value = device.get(self._sensor_key)

        if self._sensor_key in self.ENERGY_KEYS | self.POWER_KEYS:
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        if self._is_vision_data() and self._sensor_key in (
            "guenstigste_startzeit",
        ):
            if value:
                try:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return dt.isoformat()
                except Exception:
                    return value

        return value

    @property
    def extra_state_attributes(self) -> dict:
        device = self.coordinator.data.get(self._device_id, {})
        attrs = dict(device) if isinstance(device, dict) else {}

        if self._sensor_key in self.ENERGY_KEYS:
            attrs["device_class"] = "energy"
            attrs["state_class"] = "total_increasing"
            attrs.setdefault("unit_of_measurement", "kWh")
        elif self._sensor_key in self.POWER_KEYS:
            attrs["device_class"] = "power"
            attrs["state_class"] = "measurement"
            attrs.setdefault("unit_of_measurement", "W")
        elif self._is_vision_data() and self._sensor_key in (
            "aktueller_preis",
            "guenstigste_summe",
        ):
            attrs["device_class"] = "monetary"
            attrs["state_class"] = "measurement"
            attrs.setdefault("unit_of_measurement", "€/kWh")
        elif self._is_vision_data() and self._sensor_key == "guenstigste_startzeit":
            attrs["device_class"] = "timestamp"

        return attrs

    @property
    def unit_of_measurement(self):
        if self._sensor_key in self.POWER_KEYS:
            return "W"
        if self._is_vision_data() and self._sensor_key in (
            "aktueller_preis",
            "guenstigste_summe",
        ):
            return "€/kWh"
        device = self.coordinator.data.get(self._device_id, {})
        return device.get(f"{self._sensor_key}_unit", self._unit_cached)

    def _find_meter_device_id(self) -> str:
        """Findet die device_id des Stromzählers aus den Coordinator-Daten."""
        for dev_id, dev_data in self.coordinator.data.items():
            if isinstance(dev_data, dict) and not any(
                k in dev_data for k in self.VISION_KEYS
            ):
                return dev_id
        return self._device_id

    @property
    def device_info(self) -> dict:
        if self._is_vision_data() and self._sensor_key in self.VISION_TOOLS_KEYS:
            return {
                "identifiers": {("iona", "vision_tools")},
                "name": "mein Strom Vision Tools",
                "manufacturer": "enviaM",
                "model": "Vision Optimierung",
            }
        # aktueller_preis und Meter-Sensoren → Stromzähler-Gerät
        meter_id = self._find_meter_device_id() if self._is_vision_data() else self._device_id
        return {
            "identifiers": {("iona", meter_id)},
            "name": "mein Stromzähler",
            "manufacturer": "iona",
            "model": "Stromzähler",
        }

    @property
    def device_class(self):
        if self._sensor_key in self.ENERGY_KEYS:
            return "energy"
        if self._sensor_key in self.POWER_KEYS:
            return "power"
        if self._is_vision_data() and self._sensor_key in (
            "aktueller_preis",
            "guenstigste_summe",
        ):
            return "monetary"
        if self._is_vision_data() and self._sensor_key == "guenstigste_startzeit":
            return "timestamp"
        return None

    @property
    def state_class(self):
        if self._sensor_key in self.ENERGY_KEYS:
            return "total_increasing"
        if self._sensor_key in self.POWER_KEYS:
            return "measurement"
        if self._is_vision_data() and self._sensor_key in (
            "aktueller_preis",
            "guenstigste_summe",
        ):
            return "measurement"
        return None

    @property
    def entity_category(self):
        return None

    @property
    def icon(self):
        if self._sensor_key == "source":
            device = self.coordinator.data.get(self._device_id, {})
            val = device.get("source", "")
            if val == "LAN":
                return "mdi:lan"
            if val == "WEB":
                return "mdi:cloud"
            return "mdi:help-network"
        return None


# -------------------- Setup --------------------


async def async_setup_entry(hass, entry, async_add_entities):
    """Richte die Sensor-Plattform ein."""
    logger = getLogger(__name__)

    vision_tariff_enabled = _VISION_AVAILABLE and await hass.async_add_executor_job(is_vision_enabled)
    vision_tools_enabled = _VISION_AVAILABLE and await hass.async_add_executor_job(is_vision_tools_enabled)

    async def async_load():
        return await load_all_db(hass)

    coordinator = DataUpdateCoordinator(
        hass,
        logger=logger,
        name="iona db updater",
        update_method=async_load,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    sensors = []
    for device_id, device_data in coordinator.data.items():
        if not isinstance(device_data, dict):
            continue

        is_vision = any(
            key in device_data
            for key in ("aktueller_preis", "guenstigste_startzeit", "guenstigste_summe")
        )

        if is_vision and not vision_tariff_enabled:
            continue

        for key in list(device_data.keys()):
            if key in ("device_id",) or key.endswith("_unit"):
                continue
            if is_vision and key in ("timestamp", "plz", "stunden_block"):
                continue
            if not is_vision and (key == "timestamp" or key.endswith("_timestamp")):
                continue

            # Vision Tools Sensoren nur wenn vision_tools aktiviert
            if is_vision and key in IonaSensor.VISION_TOOLS_KEYS and not vision_tools_enabled:
                continue

            sensors.append(IonaSensor(coordinator, device_id, key, device_data))

    async_add_entities(sensors, update_before_add=True)

    # Vision-Sensoren aus Registry entfernen wenn deaktiviert
    if not vision_tariff_enabled:
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(hass)
        removed = 0
        for entity_id in list(entity_registry.entities.keys()):
            if entity_id.startswith("sensor.iona_vision_"):
                entity_registry.async_remove(entity_id)
                removed += 1
        if removed:
            logger.info("%d Vision-Sensoren entfernt (vision_tariff deaktiviert)", removed)

    # Vision-Tools-Sensoren aus Registry entfernen wenn deaktiviert
    if not vision_tools_enabled:
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(hass)
        removed = 0
        for entity_id in list(entity_registry.entities.keys()):
            ent = entity_registry.entities.get(entity_id)
            if ent and ent.unique_id and ("guenstigste_startzeit" in ent.unique_id or "guenstigste_summe" in ent.unique_id):
                entity_registry.async_remove(entity_id)
                removed += 1
        if removed:
            logger.info("%d Vision-Tools-Sensoren entfernt (vision_tools deaktiviert)", removed)
