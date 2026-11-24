"""Schaltflächen je Fahrzeug: Tank- bzw. Ladevorgang simulieren (Test der Meldungen am Handy)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .vehicle import Vehicle


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    v: Vehicle = hass.data[DOMAIN]["vehicles"][entry.entry_id]
    async_add_entities([SimulateRefuel(v, "fuel")] + ([SimulateRefuel(v, "electric")] if v.phev else []))


class SimulateRefuel(ButtonEntity):
    """Schickt die Meldungen eines Tank- bzw. Ladevorgangs mit Beispielwerten (Beginn, nach 30 s der Abschluss); es wird nichts gespeichert."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gas-station"

    def __init__(self, v: Vehicle, energy: str) -> None:
        self.v = v
        self.energy = energy
        key = "simulate_charge" if energy == "electric" and v.phev else "simulate_refuel"
        self._attr_unique_id = f"{v.entry.entry_id}_{key}"
        self._attr_translation_key = key
        if key == "simulate_charge":
            self._attr_icon = "mdi:ev-station"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, v.entry.entry_id)}, name=f"Drive Energy Doc {v.name}", manufacturer="Drive Energy Doc")

    async def async_press(self) -> None:
        self.hass.async_create_background_task(self.v.simulate_refuel("both", 30, self.energy), "drive_energy_doc_simulate")   # nicht blockieren: zwischen Beginn und Abschluss liegen 30 Sekunden
