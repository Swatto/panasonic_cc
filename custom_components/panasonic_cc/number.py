import logging
from typing import Callable
from dataclasses import dataclass

from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)

from aio_panasonic_comfort_cloud import (
    PanasonicDevice,
    PanasonicDeviceZone,
    ChangeRequestBuilder,
)

from . import DOMAIN
from .const import DATA_COORDINATORS, AQUAREA_COORDINATORS
from .coordinator import PanasonicDeviceCoordinator, AquareaDeviceCoordinator
from .base import PanasonicDataEntity


@dataclass(frozen=True, kw_only=True)
class PanasonicNumberEntityDescription(NumberEntityDescription):
    """Describes Panasonic Number entity."""

    get_value: Callable[[PanasonicDevice], int]
    set_value: Callable[[ChangeRequestBuilder, int], ChangeRequestBuilder]


def create_zone_damper_description(zone: PanasonicDeviceZone):
    return PanasonicNumberEntityDescription(
        key=f"zone-{zone.id}-damper",
        translation_key=f"zone-{zone.id}-damper",
        name=f"{zone.name} Damper Position",
        icon="mdi:valve",
        native_unit_of_measurement=PERCENTAGE,
        native_max_value=100,
        native_min_value=0,
        native_step=10,
        mode=NumberMode.SLIDER,
        get_value=lambda device: zone.level,
        set_value=lambda builder, value: builder.set_zone_damper(zone.id, value),
    )



async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    devices = []
    data_coordinators: list[PanasonicDeviceCoordinator] = hass.data[DOMAIN][DATA_COORDINATORS]
    aquarea_coordinators = hass.data[DOMAIN].get(AQUAREA_COORDINATORS, [])

    for data_coordinator in data_coordinators:
        if data_coordinator.device.has_zones:
            for zone in data_coordinator.device.parameters.zones:
                devices.append(PanasonicNumberEntity(data_coordinator, create_zone_damper_description(zone)))

    # --- Aquarea numbers ---
    for coordinator in aquarea_coordinators:
        device = coordinator.device
        # Target temperature
        if hasattr(device, "has_target_temperature") and getattr(device, "has_target_temperature", False):
            temp_desc = PanasonicNumberEntityDescription(
                key="target_temperature",
                translation_key="target_temperature",
                name="Target Temperature",
                icon="mdi:thermometer",
                native_unit_of_measurement="°C",
                native_max_value=getattr(device, "max_temp", 35),
                native_min_value=getattr(device, "min_temp", 5),
                native_step=0.5,
                mode=NumberMode.SLIDER,
                get_value=lambda dev: getattr(dev, "target_temperature", None),
                set_value=lambda builder, value: builder.set_target_temperature(value),
            )
            devices.append(PanasonicNumberEntity(coordinator, temp_desc))
        # Tank temperature
        if hasattr(device, "has_tank_temperature") and getattr(device, "has_tank_temperature", False):
            tank_desc = PanasonicNumberEntityDescription(
                key="tank_temperature",
                translation_key="tank_temperature",
                name="Tank Temperature",
                icon="mdi:water-boiler",
                native_unit_of_measurement="°C",
                native_max_value=getattr(device, "tank_max_temp", 65),
                native_min_value=getattr(device, "tank_min_temp", 30),
                native_step=0.5,
                mode=NumberMode.SLIDER,
                get_value=lambda dev: getattr(dev, "tank_temperature", None),
                set_value=lambda builder, value: builder.set_tank_temperature(value),
            )
            devices.append(PanasonicNumberEntity(coordinator, tank_desc))
        # Zone temperatures
        if hasattr(device, "zones"):
            for zone in getattr(device, "zones", {}).values():
                if hasattr(zone, "has_target_temperature") and getattr(zone, "has_target_temperature", False):
                    zone_desc = PanasonicNumberEntityDescription(
                        key=f"zone_{getattr(zone, 'id', 'x')}_target_temp",
                        translation_key=f"zone_{getattr(zone, 'id', 'x')}_target_temp",
                        name=f"Zone {getattr(zone, 'name', 'X')} Target Temp",
                        icon="mdi:thermometer",
                        native_unit_of_measurement="°C",
                        native_max_value=getattr(zone, "max_temp", 35),
                        native_min_value=getattr(zone, "min_temp", 5),
                        native_step=0.5,
                        mode=NumberMode.SLIDER,
                        get_value=lambda dev, z=zone: getattr(z, "target_temperature", None),
                        set_value=lambda builder, value, z=zone: builder.set_zone_target_temperature(getattr(z, 'id', 0), value),
                    )
                    devices.append(PanasonicNumberEntity(coordinator, zone_desc))
        # Otros parámetros numéricos
        # (Agregar aquí más parámetros detectados dinámicamente si la API los expone)

    async_add_entities(devices)


class PanasonicNumberEntity(PanasonicDataEntity, NumberEntity):

    entity_description: PanasonicNumberEntityDescription

    def __init__(
        self,
        coordinator: PanasonicDeviceCoordinator,
        description: PanasonicNumberEntityDescription,
    ):
        self.entity_description = description
        super().__init__(coordinator, description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        value = int(value)
        builder = self.coordinator.get_change_request_builder()
        self.entity_description.set_value(builder, value)
        await self.coordinator.async_apply_changes(builder)
        self._attr_native_value = value
        self.async_write_ha_state()

    def _async_update_attrs(self) -> None:
        self._attr_native_value = self.entity_description.get_value(
            self.coordinator.device
        )
