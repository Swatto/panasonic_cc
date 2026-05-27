from typing import Callable, Awaitable, Any
from dataclasses import dataclass
import logging

import aioaquarea

from homeassistant.core import HomeAssistant
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from .const import DOMAIN, DATA_COORDINATORS, ENERGY_COORDINATORS, AQUAREA_COORDINATORS
from .coordinator import PanasonicDeviceCoordinator, PanasonicDeviceEnergyCoordinator, AquareaDeviceCoordinator
from .base import PanasonicDataEntity, AquareaDataEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PanasonicButtonEntityDescription(ButtonEntityDescription):
    """Describes a Panasonic Button entity."""

    func: Callable[[PanasonicDeviceCoordinator], Awaitable[Any]] | None = None


APP_VERSION_DESCRIPTION = PanasonicButtonEntityDescription(
    key="update_app_version",
    name="Fetch latest app version",
    icon="mdi:refresh",
    entity_category=EntityCategory.DIAGNOSTIC,
    func=lambda coordinator: coordinator.api_client.update_app_version(),
)

UPDATE_DATA_DESCRIPTION = ButtonEntityDescription(
    key="update_data",
    name="Fetch latest data",
    icon="mdi:update",
    entity_category=EntityCategory.DIAGNOSTIC,
)
UPDATE_ENERGY_DESCRIPTION = ButtonEntityDescription(
    key="update_energy",
    name="Fetch latest energy data",
    icon="mdi:update",
    entity_category=EntityCategory.DIAGNOSTIC,
)



async def async_setup_entry(hass: HomeAssistant, config, async_add_entities):
    entities: list[ButtonEntity] = []
    data_coordinators: list[PanasonicDeviceCoordinator] = hass.data[DOMAIN][DATA_COORDINATORS]
    energy_coordinators: list[PanasonicDeviceEnergyCoordinator] = hass.data[DOMAIN][ENERGY_COORDINATORS]
    aquarea_coordinators = hass.data[DOMAIN].get(AQUAREA_COORDINATORS, [])

    for data_coordinator in data_coordinators:
        entities.append(PanasonicButtonEntity(data_coordinator, APP_VERSION_DESCRIPTION))
        entities.append(
            CoordinatorUpdateButtonEntity(data_coordinator, UPDATE_DATA_DESCRIPTION)
        )
    for energy_coordinator in energy_coordinators:
        entities.append(
            CoordinatorUpdateButtonEntity(energy_coordinator, UPDATE_ENERGY_DESCRIPTION)
        )

    # --- Aquarea buttons ---
    for aquarea_coordinator in aquarea_coordinators:
        entities.append(AquareaDefrostButton(aquarea_coordinator))

    async_add_entities(entities)


class PanasonicButtonEntity(PanasonicDataEntity, ButtonEntity):
    """Representation of a Panasonic Button."""

    entity_description: PanasonicButtonEntityDescription

    def __init__(
        self,
        coordinator: PanasonicDeviceCoordinator,
        description: PanasonicButtonEntityDescription,
    ) -> None:
        self.entity_description = description
        super().__init__(coordinator, description.key)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the entity."""

    async def async_press(self) -> None:
        """Press the button."""
        if self.entity_description.func:
            await self.entity_description.func(self.coordinator)


class CoordinatorUpdateButtonEntity(CoordinatorEntity[DataUpdateCoordinator[Any]], ButtonEntity):
    """Representation of a Coordinator Update Button."""

    def __init__(
        self, coordinator: DataUpdateCoordinator[Any], description: ButtonEntityDescription
    ) -> None:
        self.entity_description = description
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_translation_key = description.key
        device_id = getattr(coordinator, "device_id", coordinator.name)
        self._attr_unique_id = f"{device_id}-{description.key}"
        if device_info := getattr(coordinator, "device_info", None):
            self._attr_device_info = device_info

    def _async_update_attrs(self) -> None:
        """Update the attributes of the entity."""

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.async_request_refresh()


class AquareaDefrostButton(AquareaDataEntity, ButtonEntity):
    """Button to request defrost on an Aquarea device."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "request_defrost")
        self._attr_icon = "mdi:snowflake-melt"

    def _async_update_attrs(self) -> None:
        pass

    async def async_press(self) -> None:
        if self.coordinator.device.device_mode_status is not aioaquarea.DeviceModeStatus.DEFROST:
            await self.coordinator.device.request_defrost()
