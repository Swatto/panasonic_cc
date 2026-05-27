"""Tests for Aquarea climate write operations.

Verifies optimistic updates, rollback on exception, and correct device method calls.
"""

from unittest.mock import AsyncMock, MagicMock

import aioaquarea
import pytest

from custom_components.panasonic_cc import climate
from custom_components.panasonic_cc.climate import AquareaClimateEntity
from custom_components.panasonic_cc.const import (
    AQUAREA_COORDINATORS,
    DATA_COORDINATORS,
    DOMAIN,
)
from homeassistant.components.climate import HVACMode


def _setup_hass(hass, aquarea_coordinators):
    hass.data[DOMAIN] = {
        DATA_COORDINATORS: [],
        AQUAREA_COORDINATORS: aquarea_coordinators,
    }


def _make_climate_device():
    """Create a mock device suitable for climate entity creation."""
    zone = MagicMock()
    zone.zone_id = 1
    zone.name = "Zone 1"
    zone.temperature = 22
    zone.operation_status = aioaquarea.OperationStatus.ON
    zone.supports_set_temperature = True
    zone.heat_target_temperature = 25
    zone.cool_target_temperature = 20
    zone.heat_min = 16
    zone.heat_max = 30
    zone.cool_min = 16
    zone.cool_max = 30
    zone.cool_mode = True

    device = MagicMock()
    device.has_tank = False
    device.tank = None
    device.zones = {1: zone}
    device.mode = aioaquarea.ExtendedOperationMode.HEAT
    device.operation_status = aioaquarea.OperationStatus.ON
    device.current_direction = aioaquarea.DeviceDirection.PUMP
    device.support_cooling = MagicMock(return_value=True)
    device.support_special_status = True
    device.special_status = None
    device.set_mode = AsyncMock()
    device.set_temperature = AsyncMock()
    device.set_special_status = AsyncMock()
    device.turn_on = AsyncMock()
    device.turn_off = AsyncMock()
    device.device_id = "test-climate-device"
    return device


@pytest.fixture
def climate_device():
    return _make_climate_device()


@pytest.fixture
def climate_coordinator(climate_device):
    coordinator = MagicMock()
    coordinator.device = climate_device
    coordinator.device_id = "test-climate-device"
    coordinator.device_info = MagicMock()
    return coordinator


def _patch_entity(entity, hass):
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()


def _mock_create_task(hass):
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())


async def test_set_hvac_mode_calls_device(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)

    await entity.async_set_hvac_mode(HVACMode.COOL)

    climate_device.set_mode.assert_called_once_with(
        aioaquarea.UpdateOperationMode.COOL, 1
    )
    assert entity._attr_hvac_mode == HVACMode.COOL
    hass.async_create_task.assert_called_once()


async def test_set_hvac_mode_rollback_on_error(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    climate_device.set_mode = AsyncMock(side_effect=RuntimeError("API error"))
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)
    entity._attr_hvac_mode = HVACMode.HEAT

    with pytest.raises(RuntimeError):
        await entity.async_set_hvac_mode(HVACMode.COOL)

    # Should have rolled back
    assert entity._attr_hvac_mode == HVACMode.HEAT


async def test_set_temperature_calls_device(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)

    await entity.async_set_temperature(temperature=23.0)

    climate_device.set_temperature.assert_called_once_with(23, 1)
    assert entity._attr_target_temperature == 23.0


async def test_set_temperature_rollback_on_error(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    climate_device.set_temperature = AsyncMock(side_effect=RuntimeError("fail"))
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)
    entity._attr_target_temperature = 25.0

    with pytest.raises(RuntimeError):
        await entity.async_set_temperature(temperature=20.0)

    assert entity._attr_target_temperature == 25.0


async def test_set_preset_mode_calls_device(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)

    await entity.async_set_preset_mode("eco")

    climate_device.set_special_status.assert_called_once_with(aioaquarea.SpecialStatus.ECO)


async def test_set_preset_mode_rollback_on_error(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    climate_device.set_special_status = AsyncMock(side_effect=RuntimeError("fail"))
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)
    entity._attr_preset_mode = "none"

    with pytest.raises(RuntimeError):
        await entity.async_set_preset_mode("eco")

    assert entity._attr_preset_mode == "none"


async def test_turn_on_calls_device(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)

    await entity.async_turn_on()

    climate_device.turn_on.assert_called_once()
    assert entity._attr_hvac_mode == HVACMode.HEAT


async def test_turn_off_calls_device(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)

    await entity.async_turn_off()

    climate_device.turn_off.assert_called_once()
    assert entity._attr_hvac_mode == HVACMode.OFF


async def test_turn_off_rollback_on_error(hass, climate_coordinator, climate_device):
    _mock_create_task(hass)
    climate_device.turn_off = AsyncMock(side_effect=RuntimeError("fail"))
    entity = AquareaClimateEntity(climate_coordinator, 1)
    _patch_entity(entity, hass)
    entity._attr_hvac_mode = HVACMode.HEAT

    with pytest.raises(RuntimeError):
        await entity.async_turn_off()

    assert entity._attr_hvac_mode == HVACMode.HEAT


async def test_schedule_refresh_requests_forced_refresh(monkeypatch, climate_coordinator):
    sleep = AsyncMock()
    monkeypatch.setattr(climate.asyncio, "sleep", sleep)
    climate_coordinator.async_request_refresh = AsyncMock()
    entity = AquareaClimateEntity(climate_coordinator, 1)

    await entity._schedule_refresh()

    sleep.assert_awaited_once_with(climate.CLIMATE_DELAY_SHORT)
    climate_coordinator.async_request_refresh.assert_awaited_once_with(force_fetch=True)


async def test_cool_auto_modes_conditional(hass, climate_coordinator, climate_device):
    """COOL/AUTO only exposed if device supports cooling."""
    climate_device.support_cooling = MagicMock(return_value=True)
    entity = AquareaClimateEntity(climate_coordinator, 1)
    assert HVACMode.COOL in entity._attr_hvac_modes
    assert HVACMode.AUTO in entity._attr_hvac_modes

    climate_device.support_cooling = MagicMock(return_value=False)
    climate_device.zones[1].cool_max = None
    entity2 = AquareaClimateEntity(climate_coordinator, 1)
    assert HVACMode.COOL not in entity2._attr_hvac_modes
    assert HVACMode.AUTO not in entity2._attr_hvac_modes
