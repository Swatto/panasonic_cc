"""Support for Panasonic Nanoe."""

import asyncio
import logging
from typing import Any, Callable
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from aio_panasonic_comfort_cloud import (
    constants,
    PanasonicDevice,
    PanasonicDeviceZone,
    ChangeRequestBuilder,
)
import aioaquarea
from aioaquarea.errors import RequestFailedError


from . import DOMAIN
from .const import (
    DATA_COORDINATORS,
    CONF_FORCE_ENABLE_NANOE,
    DEFAULT_FORCE_ENABLE_NANOE,
    AQUAREA_COORDINATORS,
)
from .coordinator import PanasonicDeviceCoordinator, AquareaDeviceCoordinator
from .base import PanasonicDataEntity, AquareaDataEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PanasonicSwitchEntityDescription(SwitchEntityDescription):
    """Describes Panasonic Switch entity."""

    on_func: Callable[[ChangeRequestBuilder], ChangeRequestBuilder]
    off_func: Callable[[ChangeRequestBuilder], ChangeRequestBuilder]
    get_state: Callable[[PanasonicDevice], bool]
    is_available: Callable[[PanasonicDevice], bool]


NANOE_DESCRIPTION = PanasonicSwitchEntityDescription(
    key="nanoe",
    translation_key="nanoe",
    name="Nanoe",
    icon="mdi:virus-off",
    on_func=lambda builder: builder.set_nanoe_mode(constants.NanoeMode.On),
    off_func=lambda builder: builder.set_nanoe_mode(constants.NanoeMode.Off),
    get_state=lambda device: device.parameters.nanoe_mode
    in [constants.NanoeMode.On, constants.NanoeMode.ModeG, constants.NanoeMode.All],
    is_available=lambda device: device.has_nanoe,
)
ECONAVI_DESCRIPTION = PanasonicSwitchEntityDescription(
    key="eco-navi",
    translation_key="eco-navi",
    name="ECONAVI",
    icon="mdi:leaf",
    on_func=lambda builder: builder.set_eco_navi_mode(constants.EcoNaviMode.On),
    off_func=lambda builder: builder.set_eco_navi_mode(constants.EcoNaviMode.Off),
    get_state=lambda device: device.parameters.eco_navi_mode
    == constants.EcoNaviMode.On,
    is_available=lambda device: device.has_eco_navi,
)
ECO_FUNCTION_DESCRIPTION = PanasonicSwitchEntityDescription(
    key="eco-function",
    translation_key="eco-function",
    name="AI ECO",
    icon="mdi:leaf",
    on_func=lambda builder: builder.set_eco_function_mode(constants.EcoFunctionMode.On),
    off_func=lambda builder: builder.set_eco_function_mode(
        constants.EcoFunctionMode.Off
    ),
    get_state=lambda device: device.parameters.eco_function_mode
    == constants.EcoFunctionMode.On,
    is_available=lambda device: device.has_eco_function,
)
IAUTOX_DESCRIPTION = PanasonicSwitchEntityDescription(
    key="iauto-x",
    translation_key="iauto-x",
    name="iAUTO-X",
    icon="mdi:snowflake",
    on_func=lambda builder: builder.set_iautox_mode(constants.IAutoXMode.On),
    off_func=lambda builder: builder.set_iautox_mode(constants.IAutoXMode.Off),
    get_state=lambda device: device.parameters.iautox_mode == constants.IAutoXMode.On
    and device.parameters.mode == constants.OperationMode.Auto,
    is_available=lambda device: device.has_iauto_x,
)


def create_zone_mode_description(zone: PanasonicDeviceZone):
    return PanasonicSwitchEntityDescription(
        key=f"zone-{zone.id}",
        translation_key=f"zone-{zone.id}",
        name=zone.name,
        icon="mdi:thermostat",
        off_func=lambda builder: builder.set_zone_mode(zone.id, constants.ZoneMode.Off),
        on_func=lambda builder: builder.set_zone_mode(zone.id, constants.ZoneMode.On),
        get_state=lambda device: device.parameters.get_zone(zone.id).mode
        == constants.ZoneMode.On,
        is_available=lambda device: True,
    )



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    devices = []
    data_coordinators: list[PanasonicDeviceCoordinator] = hass.data[DOMAIN][DATA_COORDINATORS]
    aquarea_coordinators = hass.data[DOMAIN].get(AQUAREA_COORDINATORS, [])
    force_enable_nanoe = entry.options.get(CONF_FORCE_ENABLE_NANOE, DEFAULT_FORCE_ENABLE_NANOE)

    # Comfort Cloud switches (legacy)
    for data_coordinator in data_coordinators:
        device = data_coordinator.device
        devices.append(PanasonicSwitchEntity(data_coordinator, NANOE_DESCRIPTION, always_available=force_enable_nanoe))
        if device.has_eco_navi:
            devices.append(PanasonicSwitchEntity(data_coordinator, ECONAVI_DESCRIPTION))
        if device.has_eco_function:
            devices.append(PanasonicSwitchEntity(data_coordinator, ECO_FUNCTION_DESCRIPTION))
        if device.has_iauto_x:
            devices.append(PanasonicSwitchEntity(data_coordinator, IAUTOX_DESCRIPTION))
        if data_coordinator.device.has_zones:
            for zone in data_coordinator.device.parameters.zones:
                devices.append(PanasonicSwitchEntity(data_coordinator, create_zone_mode_description(zone)))

    # --- Aquarea switches ---
    for coordinator in aquarea_coordinators:
        device = coordinator.device
        if device.has_tank:
            devices.append(AquareaForceDHWSwitch(coordinator))
        devices.append(AquareaForceHeaterSwitch(coordinator))
        devices.append(AquareaHolidayTimerSwitch(coordinator))

    async_add_entities(devices)


class PanasonicSwitchEntityBase(SwitchEntity):
    """Base class for all Panasonic switch entities."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    entity_description: PanasonicSwitchEntityDescription  # type: ignore[override]


class PanasonicSwitchEntity(PanasonicDataEntity, PanasonicSwitchEntityBase):
    """Representation of a Panasonic switch."""

    def __init__(
        self,
        coordinator: PanasonicDeviceCoordinator,
        description: PanasonicSwitchEntityDescription,
        always_available: bool = False,
    ):
        """Initialize the Switch."""
        self.entity_description = description
        self._always_available = always_available
        super().__init__(coordinator, description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._always_available or self.entity_description.is_available(
            self.coordinator.device
        )

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        self._attr_available = self._always_available or self.entity_description.is_available(
            self.coordinator.device
        )
        self._attr_is_on = self.entity_description.get_state(self.coordinator.device)

    async def async_turn_on(self, **kwargs):
        """Turn on the Switch."""
        builder = self.coordinator.get_change_request_builder()
        self.entity_description.on_func(builder)
        await self.coordinator.async_apply_changes(builder)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off the Switch."""
        builder = self.coordinator.get_change_request_builder()
        self.entity_description.off_func(builder)
        await self.coordinator.async_apply_changes(builder)
        self._attr_is_on = False
        self.async_write_ha_state()

SWITCH_DELAY = 10.0


class AquareaForceDHWSwitch(AquareaDataEntity, SwitchEntity):
    """Force DHW switch for Aquarea devices with a tank."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "force_dhw")
        self._optimistic_is_on: bool | None = None

    @property
    def icon(self) -> str:
        return "mdi:water-boiler" if self.is_on else "mdi:water-boiler-off"

    @property
    def is_on(self) -> bool:
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        return self.coordinator.device.force_dhw is aioaquarea.ForceDHW.ON

    def _async_update_attrs(self) -> None:
        self._attr_is_on = self.coordinator.device.force_dhw is aioaquarea.ForceDHW.ON

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(SWITCH_DELAY)
        self._optimistic_is_on = None
        try:
            await self.coordinator.async_request_refresh(force_fetch=True)
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_turn_on(self, **kwargs) -> None:
        self._optimistic_is_on = True
        self.async_write_ha_state()
        await self.coordinator.device.set_force_dhw(aioaquarea.ForceDHW.ON)
        self.hass.async_create_task(self._schedule_refresh())

    async def async_turn_off(self, **kwargs) -> None:
        self._optimistic_is_on = False
        self.async_write_ha_state()
        await self.coordinator.device.set_force_dhw(aioaquarea.ForceDHW.OFF)
        self.hass.async_create_task(self._schedule_refresh())


class AquareaForceHeaterSwitch(AquareaDataEntity, SwitchEntity):
    """Force Heater switch for Aquarea devices."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "force_heater")
        self._optimistic_is_on: bool | None = None

    @property
    def icon(self) -> str:
        return "mdi:hvac" if self.is_on else "mdi:hvac-off"

    @property
    def is_on(self) -> bool:
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        return self.coordinator.device.force_heater is aioaquarea.ForceHeater.ON

    def _async_update_attrs(self) -> None:
        self._attr_is_on = self.coordinator.device.force_heater is aioaquarea.ForceHeater.ON

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(SWITCH_DELAY)
        self._optimistic_is_on = None
        try:
            await self.coordinator.async_request_refresh(force_fetch=True)
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_turn_on(self, **kwargs) -> None:
        self._optimistic_is_on = True
        self.async_write_ha_state()
        await self.coordinator.device.set_force_heater(aioaquarea.ForceHeater.ON)
        self.hass.async_create_task(self._schedule_refresh())

    async def async_turn_off(self, **kwargs) -> None:
        self._optimistic_is_on = False
        self.async_write_ha_state()
        await self.coordinator.device.set_force_heater(aioaquarea.ForceHeater.OFF)
        self.hass.async_create_task(self._schedule_refresh())


class AquareaHolidayTimerSwitch(AquareaDataEntity, SwitchEntity):
    """Holiday Timer switch for Aquarea devices."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "holiday_timer")
        self._optimistic_is_on: bool | None = None

    @property
    def icon(self) -> str:
        return "mdi:timer-check" if self.is_on else "mdi:timer-off"

    @property
    def is_on(self) -> bool:
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        return self.coordinator.device.holiday_timer is aioaquarea.HolidayTimer.ON

    def _async_update_attrs(self) -> None:
        self._attr_is_on = self.coordinator.device.holiday_timer is aioaquarea.HolidayTimer.ON

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(SWITCH_DELAY)
        self._optimistic_is_on = None
        try:
            await self.coordinator.async_request_refresh(force_fetch=True)
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_turn_on(self, **kwargs) -> None:
        self._optimistic_is_on = True
        self.async_write_ha_state()
        await self.coordinator.device.set_holiday_timer(aioaquarea.HolidayTimer.ON)
        self.hass.async_create_task(self._schedule_refresh())

    async def async_turn_off(self, **kwargs) -> None:
        self._optimistic_is_on = False
        self.async_write_ha_state()
        await self.coordinator.device.set_holiday_timer(aioaquarea.HolidayTimer.OFF)
        self.hass.async_create_task(self._schedule_refresh())

