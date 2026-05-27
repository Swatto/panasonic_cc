"""Tests for Aquarea switch write operations.

Verifies that turn_on/off calls the correct device methods and that
optimistic state + _schedule_refresh behave correctly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import aioaquarea
import pytest

from custom_components.panasonic_cc import switch
from custom_components.panasonic_cc.switch import (
    AquareaForceDHWSwitch,
    AquareaForceHeaterSwitch,
    AquareaHolidayTimerSwitch,
)
from custom_components.panasonic_cc.const import (
    AQUAREA_COORDINATORS,
    DATA_COORDINATORS,
    DOMAIN,
)


def _setup_hass(hass, aquarea_coordinators):
    hass.data[DOMAIN] = {
        DATA_COORDINATORS: [],
        AQUAREA_COORDINATORS: aquarea_coordinators,
    }


async def _collect_switches(hass, coordinators):
    switches = []
    _setup_hass(hass, coordinators)
    await switch.async_setup_entry(hass, MagicMock(), lambda e, **kw: switches.extend(e))
    return switches


def _patch_entity(entity, hass):
    """Patch entity for direct testing (no platform)."""
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()


def _mock_create_task(hass):
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())


async def test_force_dhw_turn_on_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_force_dhw = AsyncMock()
    _mock_create_task(hass)
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fd = next(s for s in switches if isinstance(s, AquareaForceDHWSwitch))
    _patch_entity(fd, hass)

    await fd.async_turn_on()

    mock_aquarea_device.set_force_dhw.assert_called_once_with(aioaquarea.ForceDHW.ON)
    assert fd._optimistic_is_on is True
    hass.async_create_task.assert_called_once()


async def test_force_dhw_turn_off_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_force_dhw = AsyncMock()
    _mock_create_task(hass)
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fd = next(s for s in switches if isinstance(s, AquareaForceDHWSwitch))
    _patch_entity(fd, hass)

    await fd.async_turn_off()

    mock_aquarea_device.set_force_dhw.assert_called_once_with(aioaquarea.ForceDHW.OFF)
    assert fd._optimistic_is_on is False


async def test_schedule_refresh_clears_optimistic_state(
    monkeypatch, mock_aquarea_coordinator
):
    sleep = AsyncMock()
    monkeypatch.setattr(switch.asyncio, "sleep", sleep)
    mock_aquarea_coordinator.async_request_refresh = AsyncMock()
    fd = AquareaForceDHWSwitch(mock_aquarea_coordinator)
    fd._optimistic_is_on = True

    await fd._schedule_refresh()

    sleep.assert_awaited_once_with(switch.SWITCH_DELAY)
    assert fd._optimistic_is_on is None
    mock_aquarea_coordinator.async_request_refresh.assert_awaited_once_with(
        force_fetch=True
    )


async def test_force_heater_turn_on_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_force_heater = AsyncMock()
    _mock_create_task(hass)
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fh = next(s for s in switches if isinstance(s, AquareaForceHeaterSwitch))
    _patch_entity(fh, hass)

    await fh.async_turn_on()

    mock_aquarea_device.set_force_heater.assert_called_once_with(aioaquarea.ForceHeater.ON)


async def test_holiday_timer_turn_on_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_holiday_timer = AsyncMock()
    _mock_create_task(hass)
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    ht = next(s for s in switches if isinstance(s, AquareaHolidayTimerSwitch))
    _patch_entity(ht, hass)

    await ht.async_turn_on()

    mock_aquarea_device.set_holiday_timer.assert_called_once_with(aioaquarea.HolidayTimer.ON)


async def test_holiday_timer_turn_off_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_holiday_timer = AsyncMock()
    _mock_create_task(hass)
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    ht = next(s for s in switches if isinstance(s, AquareaHolidayTimerSwitch))
    _patch_entity(ht, hass)

    await ht.async_turn_off()

    mock_aquarea_device.set_holiday_timer.assert_called_once_with(aioaquarea.HolidayTimer.OFF)
