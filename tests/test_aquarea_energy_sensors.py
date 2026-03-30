"""Tests for Aquarea energy consumption sensor parsing.

Verifies that accumulated and hourly energy sensors correctly parse
consumption data from the coordinator.
"""

from datetime import datetime
from unittest.mock import MagicMock

import aioaquarea
import pytest

from custom_components.panasonic_cc.sensor import (
    AquareaEnergyAccumulatedConsumptionSensor,
    AquareaEnergyConsumptionSensor,
    AquareaEnergyConsumptionSensorDescription,
    ACCUMULATED_ENERGY_SENSORS,
    ENERGY_SENSORS,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy


def _make_consumption(data_time, heat=0.0, cool=0.0, tank=0.0, total=0.0):
    c = MagicMock()
    c.data_time = data_time
    c.heat_consumption = heat
    c.cool_consumption = cool
    c.tank_consumption = tank
    c.total_consumption = total
    return c


@pytest.fixture
def heat_acc_desc():
    return next(d for d in ACCUMULATED_ENERGY_SENSORS if d.consumption_type == aioaquarea.ConsumptionType.HEAT)


@pytest.fixture
def total_acc_desc():
    return next(d for d in ACCUMULATED_ENERGY_SENSORS if d.consumption_type == aioaquarea.ConsumptionType.TOTAL)


@pytest.fixture
def heat_hourly_desc():
    return next(d for d in ENERGY_SENSORS if d.consumption_type == aioaquarea.ConsumptionType.HEAT)


def test_accumulated_sensor_sums_month_data(mock_aquarea_coordinator, heat_acc_desc):
    mock_aquarea_coordinator.month_consumption = [
        _make_consumption("20260301", heat=1.5),
        _make_consumption("20260302", heat=2.0),
        _make_consumption("20260303", heat=0.5),
    ]

    entity = AquareaEnergyAccumulatedConsumptionSensor(heat_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    assert entity._attr_native_value == 4.0


def test_accumulated_sensor_excludes_future_dates(mock_aquarea_coordinator, heat_acc_desc):
    mock_aquarea_coordinator.month_consumption = [
        _make_consumption("20260301", heat=1.0),
        _make_consumption("20261231", heat=99.0),  # far future
    ]

    entity = AquareaEnergyAccumulatedConsumptionSensor(heat_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    assert entity._attr_native_value == 1.0


def test_accumulated_sensor_handles_empty_data(mock_aquarea_coordinator, heat_acc_desc):
    mock_aquarea_coordinator.month_consumption = None

    entity = AquareaEnergyAccumulatedConsumptionSensor(heat_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 5.0
    entity._async_update_attrs()

    # Should not change when no data
    assert entity._attr_native_value == 5.0


def test_accumulated_sensor_handles_empty_list(mock_aquarea_coordinator, heat_acc_desc):
    mock_aquarea_coordinator.month_consumption = []

    entity = AquareaEnergyAccumulatedConsumptionSensor(heat_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 5.0
    entity._async_update_attrs()

    assert entity._attr_native_value == 5.0


def test_accumulated_sensor_total_type(mock_aquarea_coordinator, total_acc_desc):
    mock_aquarea_coordinator.month_consumption = [
        _make_consumption("20260301", heat=1.0, cool=0.5, tank=0.3, total=1.8),
    ]

    entity = AquareaEnergyAccumulatedConsumptionSensor(total_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    assert entity._attr_native_value == 1.8


def test_accumulated_sensor_dash_date_format(mock_aquarea_coordinator, heat_acc_desc):
    mock_aquarea_coordinator.month_consumption = [
        _make_consumption("2026-03-01", heat=2.5),
    ]

    entity = AquareaEnergyAccumulatedConsumptionSensor(heat_acc_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    assert entity._attr_native_value == 2.5


def test_hourly_sensor_finds_previous_hour(mock_aquarea_coordinator, heat_hourly_desc):
    # The sensor looks for the previous hour's data
    from homeassistant.util import dt as dt_util
    now = dt_util.now()
    prev_hour = now.hour - 1 if now.hour > 0 else 23
    prev_date = now.date() if now.hour > 0 else (now - __import__("datetime").timedelta(days=1)).date()
    date_str = prev_date.strftime("%Y%m%d") + f" {prev_hour:02d}"

    mock_aquarea_coordinator.day_consumption = [
        _make_consumption(date_str, heat=0.75),
    ]

    entity = AquareaEnergyConsumptionSensor(heat_hourly_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    assert entity._attr_native_value == 0.75


def test_hourly_sensor_falls_back_to_last_entry(mock_aquarea_coordinator, heat_hourly_desc):
    mock_aquarea_coordinator.day_consumption = [
        _make_consumption("20260330 08", heat=0.5),
        _make_consumption("20260330 09", heat=0.6),
    ]

    entity = AquareaEnergyConsumptionSensor(heat_hourly_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 0
    entity._async_update_attrs()

    # Should fall back to last available entry (09) if target hour not found
    assert entity._attr_native_value is not None


def test_hourly_sensor_handles_empty_data(mock_aquarea_coordinator, heat_hourly_desc):
    mock_aquarea_coordinator.day_consumption = None

    entity = AquareaEnergyConsumptionSensor(heat_hourly_desc, mock_aquarea_coordinator)
    entity._attr_native_value = 3.0
    entity._async_update_attrs()

    # Should not change when no data
    assert entity._attr_native_value == 3.0


def test_exists_fn_filters_cooling_sensors(mock_aquarea_coordinator, mock_aquarea_device):
    """Cooling sensors should only exist if any zone has cool_mode."""
    mock_aquarea_device.zones[1].cool_mode = False
    cool_desc = next(d for d in ACCUMULATED_ENERGY_SENSORS if d.consumption_type == aioaquarea.ConsumptionType.COOL)
    assert cool_desc.exists_fn(mock_aquarea_coordinator) is False

    mock_aquarea_device.zones[1].cool_mode = True
    assert cool_desc.exists_fn(mock_aquarea_coordinator) is True


def test_exists_fn_filters_tank_sensors(mock_aquarea_coordinator, mock_aquarea_device):
    """Tank sensors should only exist if device has a tank."""
    tank_desc = next(d for d in ACCUMULATED_ENERGY_SENSORS if d.consumption_type == aioaquarea.ConsumptionType.WATER_TANK)
    mock_aquarea_device.has_tank = True
    assert tank_desc.exists_fn(mock_aquarea_coordinator) is True

    mock_aquarea_device.has_tank = False
    assert tank_desc.exists_fn(mock_aquarea_coordinator) is False
