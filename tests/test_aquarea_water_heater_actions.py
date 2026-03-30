"""Tests for Aquarea water heater write operations."""

from unittest.mock import AsyncMock, MagicMock

import aioaquarea
from aioaquarea.data import DeviceAction, DeviceDirection, OperationStatus
import pytest

from custom_components.panasonic_cc import water_heater
from custom_components.panasonic_cc.water_heater import AquareaWaterHeater
from custom_components.panasonic_cc.const import (
    AQUAREA_COORDINATORS,
    DOMAIN,
    STATE_HEATING,
    STATE_IDLE,
)
from homeassistant.const import STATE_OFF


@pytest.fixture
def wh_device():
    tank = MagicMock()
    tank.heat_min = 40
    tank.heat_max = 65
    tank.target_temperature = 50
    tank.temperature = 48
    tank.operation_status = OperationStatus.ON
    tank.set_target_temperature = AsyncMock()
    tank.turn_on = AsyncMock()
    tank.turn_off = AsyncMock()

    device = MagicMock()
    device.has_tank = True
    device.tank = tank
    device.is_on_error = False
    device.current_direction = DeviceDirection.IDLE
    device.current_action = DeviceAction.IDLE
    device.device_id = "test-wh"
    return device


@pytest.fixture
def wh_coordinator(wh_device):
    coordinator = MagicMock()
    coordinator.device = wh_device
    coordinator.device_id = "test-wh"
    coordinator.device_info = MagicMock()
    return coordinator


def _patch_entity(entity, hass):
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()


async def test_set_temperature_calls_tank(hass, wh_coordinator, wh_device):
    hass.async_create_task = MagicMock()
    entity = AquareaWaterHeater(wh_coordinator)
    _patch_entity(entity, hass)

    await entity.async_set_temperature(temperature=55.0)

    wh_device.tank.set_target_temperature.assert_called_once_with(55)
    assert entity._attr_target_temperature == 55.0
    hass.async_create_task.assert_called_once()


async def test_set_operation_mode_heating(hass, wh_coordinator, wh_device):
    hass.async_create_task = MagicMock()
    entity = AquareaWaterHeater(wh_coordinator)
    _patch_entity(entity, hass)

    await entity.async_set_operation_mode(STATE_HEATING)

    wh_device.tank.turn_on.assert_called_once()


async def test_set_operation_mode_off(hass, wh_coordinator, wh_device):
    hass.async_create_task = MagicMock()
    entity = AquareaWaterHeater(wh_coordinator)
    _patch_entity(entity, hass)

    await entity.async_set_operation_mode(STATE_OFF)

    wh_device.tank.turn_off.assert_called_once()
    assert entity._attr_state == STATE_OFF


async def test_heating_detection_by_direction(wh_coordinator, wh_device):
    wh_device.current_direction = DeviceDirection.WATER
    entity = AquareaWaterHeater(wh_coordinator)
    entity._async_update_attrs()
    assert entity._attr_current_operation == STATE_HEATING


async def test_idle_when_not_heating(wh_coordinator, wh_device):
    wh_device.current_direction = DeviceDirection.IDLE
    wh_device.current_action = DeviceAction.IDLE
    entity = AquareaWaterHeater(wh_coordinator)
    entity._async_update_attrs()
    assert entity._attr_current_operation == STATE_IDLE


async def test_off_state_when_tank_off(wh_coordinator, wh_device):
    wh_device.tank.operation_status = OperationStatus.OFF
    entity = AquareaWaterHeater(wh_coordinator)
    entity._async_update_attrs()
    assert entity._attr_state == STATE_OFF
    assert entity._attr_icon == "mdi:water-boiler-off"


async def test_error_icon_when_off_and_error(wh_coordinator, wh_device):
    wh_device.tank.operation_status = OperationStatus.OFF
    wh_device.is_on_error = True
    entity = AquareaWaterHeater(wh_coordinator)
    entity._async_update_attrs()
    assert entity._attr_icon == "mdi:water-boiler-alert"
