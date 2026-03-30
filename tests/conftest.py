"""Shared fixtures for Panasonic CC integration tests."""

import pytest
from unittest.mock import MagicMock

import aioaquarea
from aioaquarea.data import Device as AquareaDevice

from custom_components.panasonic_cc.coordinator import AquareaDeviceCoordinator


@pytest.fixture
def mock_aquarea_device():
    """Mock aioaquarea Device matching real device B116146854 attributes."""
    zone = MagicMock()
    zone.zone_id = 1
    zone.name = "Zone 1"
    zone.temperature = 27
    zone.cool_mode = False

    device = MagicMock(spec=AquareaDevice)
    device.has_tank = True
    device.tank = MagicMock(temperature=53)
    device.zones = {1: zone}
    device.temperature_outdoor = 4.0
    device.is_on_error = False
    device.current_error = None
    device.holiday_timer = aioaquarea.HolidayTimer.OFF
    device.force_heater = aioaquarea.ForceHeater.OFF
    device.force_dhw = aioaquarea.ForceDHW.OFF
    device.quiet_mode = aioaquarea.QuietMode.OFF
    device.powerful_time = aioaquarea.PowerfulTime.OFF
    device.pump_duty = 0
    device.current_direction = aioaquarea.DeviceDirection.IDLE
    device.device_mode_status = aioaquarea.DeviceModeStatus.NORMAL
    return device


@pytest.fixture
def mock_aquarea_coordinator(mock_aquarea_device):
    """Mock AquareaDeviceCoordinator backed by mock_aquarea_device."""
    coordinator = MagicMock(spec=AquareaDeviceCoordinator)
    coordinator.device = mock_aquarea_device
    coordinator.device_id = "test-device-B116146854"
    coordinator.device_info = MagicMock()
    coordinator.day_consumption = None
    coordinator.month_consumption = None
    return coordinator
