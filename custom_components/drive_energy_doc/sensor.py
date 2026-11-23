"""Sensoren je Fahrzeug."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .vehicle import Vehicle, signal


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    v: Vehicle = hass.data[DOMAIN]["vehicles"][entry.entry_id]
    async_add_entities([TankStatus(v), TankLast(v), TankPrice(v), TankConsumption(v), TankCost(v)] + ([TankConsumptionElectric(v)] if v.phev else []))


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    key = ""

    def __init__(self, v: Vehicle) -> None:
        self.v = v
        self._attr_unique_id = f"{v.entry.entry_id}_{self.key}"
        self._attr_translation_key = self.key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, v.entry.entry_id)}, name=f"Drive Energy Doc {v.name}", manufacturer="Drive Energy Doc")

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, signal(self.v.entry.entry_id), self.async_write_ha_state))


class TankStatus(_Base):
    key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "candidate", "refuelling"]

    @property
    def native_value(self):
        return self.v.summary()["status"]


class TankLast(_Base):
    key = "last_refuel"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        last = self.v.summary()["last"]
        return dt_util.utc_from_timestamp(last["ts"]) if last else None

    @property
    def extra_state_attributes(self):
        last = self.v.summary()["last"] or {}
        return {**{k: last.get(k) for k in ("odometer", "station", "address", "quantity", "unit_price", "total", "level_from", "level_to", "quantity_source", "receipt")}, "license_plate": self.v.plate or None}


class TankPrice(_Base):
    key = "last_price"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        return f"€/{self.v.unit}"

    @property
    def native_value(self):
        last = self.v.summary()["last"]
        return last.get("unit_price") if last else None


class TankConsumption(_Base):
    key = "consumption"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        return f"{self.v.unit}/100 km"

    @property
    def native_value(self):
        return self.v.summary()["avg_consumption"]


class TankConsumptionElectric(_Base):
    """Plug-in-Hybrid: Stromverbrauch (kWh/100 km) neben dem Kraftstoffverbrauch."""

    key = "consumption_electric"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kWh/100 km"

    @property
    def native_value(self):
        return self.v.summary()["avg_consumption_electric"]


class TankCost(_Base):
    key = "cost_12m"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    @property
    def native_value(self):
        return self.v.summary()["cost_12m"]
