"""Tests for Aquarea switch entity registration and state.

Verifies that the concrete switch classes are registered with the correct
translation keys and that their is_on property reads the correct device state.
"""

from unittest.mock import MagicMock

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


def _keys(entities):
    """Extract translation keys from a list of entities."""
    return {e._attr_translation_key for e in entities}


async def test_holiday_timer_registered(hass, mock_aquarea_coordinator):
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    assert "holiday_timer" in _keys(switches)
    assert any(isinstance(s, AquareaHolidayTimerSwitch) for s in switches)


async def test_force_heater_registered(hass, mock_aquarea_coordinator):
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    assert "force_heater" in _keys(switches)
    assert any(isinstance(s, AquareaForceHeaterSwitch) for s in switches)


async def test_force_dhw_registered(hass, mock_aquarea_coordinator):
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    assert "force_dhw" in _keys(switches)
    assert any(isinstance(s, AquareaForceDHWSwitch) for s in switches)


async def test_force_dhw_not_registered_when_no_tank(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    mock_aquarea_device.has_tank = False
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    assert not any(isinstance(s, AquareaForceDHWSwitch) for s in switches)


async def test_holiday_timer_state_off(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.holiday_timer = aioaquarea.HolidayTimer.OFF
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    hol = next(s for s in switches if isinstance(s, AquareaHolidayTimerSwitch))
    assert hol.is_on is False


async def test_holiday_timer_state_on(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.holiday_timer = aioaquarea.HolidayTimer.ON
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    hol = next(s for s in switches if isinstance(s, AquareaHolidayTimerSwitch))
    assert hol.is_on is True


async def test_force_heater_state_off(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.force_heater = aioaquarea.ForceHeater.OFF
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fh = next(s for s in switches if isinstance(s, AquareaForceHeaterSwitch))
    assert fh.is_on is False


async def test_force_dhw_state_off(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.force_dhw = aioaquarea.ForceDHW.OFF
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fd = next(s for s in switches if isinstance(s, AquareaForceDHWSwitch))
    assert fd.is_on is False


async def test_force_dhw_optimistic_on(hass, mock_aquarea_coordinator, mock_aquarea_device):
    """Optimistic state should override device state."""
    mock_aquarea_device.force_dhw = aioaquarea.ForceDHW.OFF
    switches = await _collect_switches(hass, [mock_aquarea_coordinator])
    fd = next(s for s in switches if isinstance(s, AquareaForceDHWSwitch))
    fd._optimistic_is_on = True
    assert fd.is_on is True
