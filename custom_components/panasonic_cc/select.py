import asyncio
import logging
from typing import Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.components.select import SelectEntity, SelectEntityDescription

from .const import (
    DOMAIN,
    DATA_COORDINATORS,
    SELECT_HORIZONTAL_SWING,
    SELECT_VERTICAL_SWING,
    AQUAREA_COORDINATORS,
)
from aio_panasonic_comfort_cloud import PanasonicDevice, ChangeRequestBuilder, constants
from aioaquarea import PowerfulTime, QuietMode
from aioaquarea.errors import RequestFailedError

from .coordinator import PanasonicDeviceCoordinator, AquareaDeviceCoordinator
from .base import PanasonicDataEntity, AquareaDataEntity

_LOGGER = logging.getLogger(__name__)

SELECT_DELAY = 10.0

QUIET_MODE_LOOKUP = {
    "level1": QuietMode.LEVEL1,
    "level2": QuietMode.LEVEL2,
    "level3": QuietMode.LEVEL3,
    "off": QuietMode.OFF,
}
QUIET_MODE_REVERSE_LOOKUP = {v: k for k, v in QUIET_MODE_LOOKUP.items()}

POWERFUL_TIME_LOOKUP = {
    "on-30m": PowerfulTime.ON_30MIN,
    "on-60m": PowerfulTime.ON_60MIN,
    "on-90m": PowerfulTime.ON_90MIN,
    "off": PowerfulTime.OFF,
}
POWERFUL_TIME_REVERSE_LOOKUP = {v: k for k, v in POWERFUL_TIME_LOOKUP.items()}

@dataclass(frozen=True, kw_only=True)
class PanasonicSelectEntityDescription(SelectEntityDescription):
    """Description of a select entity."""

    set_option: Callable[[ChangeRequestBuilder, str], ChangeRequestBuilder]
    get_current_option: Callable[[PanasonicDevice], str]
    is_available: Callable[[PanasonicDevice], bool]
    get_options: Callable[[PanasonicDevice], list[str]] | None = None


HORIZONTAL_SWING_DESCRIPTION = PanasonicSelectEntityDescription(
    key=SELECT_HORIZONTAL_SWING,
    translation_key=SELECT_HORIZONTAL_SWING,
    icon="mdi:swap-horizontal",
    name="Horizontal Swing Mode",
    options=[
        opt.name
        for opt in constants.AirSwingLR
        if opt != constants.AirSwingLR.Unavailable
    ],
    set_option=lambda builder, new_value: builder.set_horizontal_swing(new_value),
    get_current_option=lambda device: device.parameters.horizontal_swing_mode.name,
    is_available=lambda device: device.has_horizontal_swing,
)
VERTICAL_SWING_DESCRIPTION = PanasonicSelectEntityDescription(
    key=SELECT_VERTICAL_SWING,
    translation_key=SELECT_VERTICAL_SWING,
    icon="mdi:swap-vertical",
    name="Vertical Swing Mode",
    get_options=lambda device: [
        opt.name
        for opt in constants.AirSwingUD
        if opt != constants.AirSwingUD.Swing or device.features.auto_swing_ud
    ],
    set_option=lambda builder, new_value: builder.set_vertical_swing(new_value),
    get_current_option=lambda device: device.parameters.vertical_swing_mode.name,
    is_available=lambda device: True,
)



async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    entities: list[SelectEntity] = []
    data_coordinators: list[PanasonicDeviceCoordinator] = hass.data[DOMAIN][DATA_COORDINATORS]
    aquarea_coordinators = hass.data[DOMAIN].get(AQUAREA_COORDINATORS, [])

    for coordinator in data_coordinators:
        entities.append(PanasonicSelectEntity(coordinator, HORIZONTAL_SWING_DESCRIPTION))
        entities.append(PanasonicSelectEntity(coordinator, VERTICAL_SWING_DESCRIPTION))

    # --- Aquarea selects ---
    for coordinator in aquarea_coordinators:
        entities.append(AquareaQuietModeSelect(coordinator))
        entities.append(AquareaPowerfulTimeSelect(coordinator))

    async_add_entities(entities)


class PanasonicSelectEntityBase(SelectEntity):
    """Base class for all select entities."""

    entity_description: PanasonicSelectEntityDescription


class PanasonicSelectEntity(PanasonicDataEntity, PanasonicSelectEntityBase):

    def __init__(
        self,
        coordinator: PanasonicDeviceCoordinator,
        description: PanasonicSelectEntityDescription,
    ):
        self.entity_description = description
        if description.get_options is not None:
            self._attr_options = description.get_options(coordinator.device)
        super().__init__(coordinator, description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.entity_description.is_available(self.coordinator.device)

    async def async_select_option(self, option: str) -> None:
        builder = self.coordinator.get_change_request_builder()
        self.entity_description.set_option(builder, option)
        await self.coordinator.async_apply_changes(builder)
        self._attr_current_option = option
        self.async_write_ha_state()

    def _async_update_attrs(self) -> None:
        self._attr_current_option = self.entity_description.get_current_option(
            self.coordinator.device
        )

class AquareaQuietModeSelect(AquareaDataEntity, SelectEntity):
    """Select entity for Aquarea quiet mode."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "quiet_mode")
        self._attr_options = list(QUIET_MODE_LOOKUP.keys())
        self._attr_icon = "mdi:volume-off"
        self._optimistic_option: str | None = None

    @property
    def current_option(self) -> str:
        if self._optimistic_option is not None:
            return self._optimistic_option
        return QUIET_MODE_REVERSE_LOOKUP.get(
            self.coordinator.device.quiet_mode, "off"
        )

    def _async_update_attrs(self) -> None:
        self._attr_current_option = QUIET_MODE_REVERSE_LOOKUP.get(
            self.coordinator.device.quiet_mode
        )

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(SELECT_DELAY)
        self._optimistic_option = None
        try:
            await self.coordinator.async_request_refresh()
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_select_option(self, option: str) -> None:
        quiet_mode = QUIET_MODE_LOOKUP.get(option)
        if quiet_mode is None:
            return
        if quiet_mode is self.coordinator.device.quiet_mode:
            return
        self._optimistic_option = option
        self.async_write_ha_state()
        await self.coordinator.device.set_quiet_mode(quiet_mode)
        self.hass.async_create_task(self._schedule_refresh())


class AquareaPowerfulTimeSelect(AquareaDataEntity, SelectEntity):
    """Select entity for Aquarea powerful time."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "powerful_time")
        self._attr_options = list(POWERFUL_TIME_LOOKUP.keys())
        self._optimistic_option: str | None = None

    @property
    def icon(self) -> str:
        if self._optimistic_option is not None:
            return "mdi:fire-off" if self._optimistic_option == "off" else "mdi:fire"
        return (
            "mdi:fire-off"
            if self.coordinator.device.powerful_time is PowerfulTime.OFF
            else "mdi:fire"
        )

    @property
    def current_option(self) -> str:
        if self._optimistic_option is not None:
            return self._optimistic_option
        return POWERFUL_TIME_REVERSE_LOOKUP.get(
            self.coordinator.device.powerful_time, "off"
        )

    def _async_update_attrs(self) -> None:
        self._attr_current_option = POWERFUL_TIME_REVERSE_LOOKUP.get(
            self.coordinator.device.powerful_time
        )

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(SELECT_DELAY)
        self._optimistic_option = None
        try:
            await self.coordinator.async_request_refresh()
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_select_option(self, option: str) -> None:
        powerful_time = POWERFUL_TIME_LOOKUP.get(option)
        if powerful_time is None:
            return
        if powerful_time is self.coordinator.device.powerful_time:
            return
        self._optimistic_option = option
        self.async_write_ha_state()
        await self.coordinator.device.set_powerful_time(powerful_time)
        self.hass.async_create_task(self._schedule_refresh())

