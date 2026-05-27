"""Support for the Aquarea Tank."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTemperature,
    STATE_OFF,
    PRECISION_WHOLE,
    ATTR_TEMPERATURE,
)
from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)

from .base import AquareaDataEntity
from .coordinator import AquareaDeviceCoordinator
from .const import DOMAIN, AQUAREA_COORDINATORS, STATE_HEATING, STATE_IDLE
from aioaquarea.data import DeviceAction, DeviceDirection, OperationStatus
from aioaquarea.errors import RequestFailedError

_LOGGER = logging.getLogger(__name__)

WATER_HEATER_DELAY = 10.0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    entities = []
    aquarea_coordinators: list[AquareaDeviceCoordinator] = hass.data[DOMAIN][
        AQUAREA_COORDINATORS
    ]
    for coordinator in aquarea_coordinators:
        if coordinator.device.has_tank:
            entities.append(AquareaWaterHeater(coordinator))
    async_add_entities(entities)


class AquareaWaterHeater(AquareaDataEntity, WaterHeaterEntity):
    """Representation of an Aquarea Water Tank."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_operation_list = [STATE_HEATING, STATE_OFF]
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "tank")

    def _async_update_attrs(self) -> None:
        device = self.coordinator.device
        if device.tank is None:
            self._attr_available = False
            return

        self._attr_min_temp = device.tank.heat_min
        self._attr_max_temp = device.tank.heat_max
        self._attr_target_temperature = device.tank.target_temperature
        self._attr_current_temperature = device.tank.temperature

        if device.tank.operation_status == OperationStatus.OFF:
            self._attr_state = STATE_OFF  # type: ignore[assignment]
            self._attr_current_operation = STATE_OFF
            self._attr_icon = (
                "mdi:water-boiler-alert"
                if device.is_on_error
                else "mdi:water-boiler-off"
            )
            return

        self._attr_icon = "mdi:water-boiler"
        self._attr_state = STATE_HEAT_PUMP  # type: ignore[assignment]

        # Determine if actively heating the tank
        current_direction = getattr(device, "current_direction", None)
        current_action = getattr(device, "current_action", None)
        is_heating = False

        if current_direction == DeviceDirection.WATER:
            is_heating = True
        else:
            try:
                if current_action in (
                    DeviceAction.HEATING_WATER,
                    DeviceAction.HEATING,
                    getattr(DeviceAction, "WATER_HEATING", None),
                ):
                    is_heating = True
                else:
                    action_name = str(current_action).upper()
                    if "HEAT" in action_name or "WATER" in action_name or "TANK" in action_name:
                        is_heating = True
            except (AttributeError, TypeError):
                is_heating = False

        self._attr_current_operation = STATE_HEATING if is_heating else STATE_IDLE

    async def _schedule_refresh(self) -> None:
        await asyncio.sleep(WATER_HEATER_DELAY)
        try:
            await self.coordinator.async_request_refresh(force_fetch=True)
        except RequestFailedError:
            _LOGGER.exception(
                "Delayed refresh failed for device %s",
                getattr(self.coordinator.device, "device_id", "unknown"),
            )

    async def async_set_temperature(self, **kwargs):
        temperature: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        self.async_write_ha_state()
        await self.coordinator.device.tank.set_target_temperature(int(temperature))
        self.hass.async_create_task(self._schedule_refresh())

    async def async_set_operation_mode(self, operation_mode):
        if operation_mode == STATE_HEATING:
            self._attr_state = STATE_HEAT_PUMP  # type: ignore[assignment]
            self._attr_current_operation = STATE_IDLE
            await self.coordinator.device.tank.turn_on()
        elif operation_mode == STATE_OFF:
            self._attr_state = STATE_OFF  # type: ignore[assignment]
            self._attr_current_operation = STATE_OFF
            await self.coordinator.device.tank.turn_off()
        self.async_write_ha_state()
        self.hass.async_create_task(self._schedule_refresh())
