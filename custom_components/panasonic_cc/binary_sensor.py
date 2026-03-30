"""Binary sensors for Aquarea devices."""

import logging

import aioaquarea

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory

from .const import DOMAIN, AQUAREA_COORDINATORS
from .base import AquareaDataEntity
from .coordinator import AquareaDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    entities = []
    aquarea_coordinators = hass.data[DOMAIN].get(AQUAREA_COORDINATORS, [])

    for coordinator in aquarea_coordinators:
        entities.append(AquareaStatusBinarySensor(coordinator))
        entities.append(AquareaDefrostBinarySensor(coordinator))

    async_add_entities(entities)


class AquareaStatusBinarySensor(AquareaDataEntity, BinarySensorEntity):
    """Binary sensor indicating if the Aquarea device is in error state."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "is_on_error")
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.coordinator.device.is_on_error

    def _async_update_attrs(self) -> None:
        self._attr_is_on = self.coordinator.device.is_on_error


class AquareaDefrostBinarySensor(AquareaDataEntity, BinarySensorEntity):
    """Binary sensor indicating if the Aquarea device is in defrost mode."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "defrost")
        self._attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def icon(self) -> str:
        return "mdi:snowflake-melt" if self.is_on else "mdi:snowflake-off"

    @property
    def is_on(self) -> bool:
        return self.coordinator.device.device_mode_status is aioaquarea.DeviceModeStatus.DEFROST

    def _async_update_attrs(self) -> None:
        self._attr_is_on = (
            self.coordinator.device.device_mode_status is aioaquarea.DeviceModeStatus.DEFROST
        )
