"""Tests for Aquarea sensor entity registration.

Verifies that async_setup_entry registers the expected sensor entities
given a mocked device.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.panasonic_cc import sensor
from custom_components.panasonic_cc.sensor import (
    AquareaSensorEntity,
    AquareaPumpDirectionSensor,
    AquareaPumpStatusSensor,
)
from custom_components.panasonic_cc.const import (
    AQUAREA_COORDINATORS,
    DATA_COORDINATORS,
    DOMAIN,
    ENERGY_COORDINATORS,
)


def _setup_hass(hass, aquarea_coordinators):
    hass.data[DOMAIN] = {
        DATA_COORDINATORS: [],
        ENERGY_COORDINATORS: [],
        AQUAREA_COORDINATORS: aquarea_coordinators,
    }


async def _collect_entities(hass, coordinators):
    entities = []
    _setup_hass(hass, coordinators)
    await sensor.async_setup_entry(hass, MagicMock(), lambda e, **kw: entities.extend(e))
    return entities


def _keys(entities):
    """Extract translation keys from entities (works for both description-based and concrete)."""
    keys = set()
    for e in entities:
        if hasattr(e, "entity_description") and hasattr(e.entity_description, "key"):
            keys.add(e.entity_description.key)
        elif hasattr(e, "_attr_translation_key"):
            keys.add(e._attr_translation_key)
    return keys


async def test_outside_temperature_always_registered(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert "outside_temperature" in _keys(entities)


async def test_tank_temperature_registered_when_has_tank(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert "tank_temperature" in _keys(entities)


async def test_tank_temperature_not_registered_when_no_tank(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    mock_aquarea_device.has_tank = False
    mock_aquarea_device.tank = None
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert "tank_temperature" not in _keys(entities)


async def test_zone_temperature_registered(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert "zone_1_temperature" in _keys(entities)


async def test_zone_temperature_not_registered_when_no_zones(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    mock_aquarea_device.zones = {}
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    keys = _keys(entities)
    assert not any(k.startswith("zone_") and k.endswith("_temperature") for k in keys)


async def test_multiple_zone_temperatures_registered(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    zone2 = MagicMock()
    zone2.zone_id = 2
    zone2.name = "Zone 2"
    zone2.temperature = None
    zone2.cool_mode = False
    mock_aquarea_device.zones = {**mock_aquarea_device.zones, 2: zone2}

    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    keys = _keys(entities)
    assert "zone_1_temperature" in keys
    assert "zone_2_temperature" in keys


async def test_error_code_always_registered(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert "error_code" in _keys(entities)


async def test_error_code_available_when_on_error(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    fault = MagicMock()
    fault.error_code = "H99"
    fault.error_message = "Sensor fault"
    mock_aquarea_device.is_on_error = True
    mock_aquarea_device.current_error = fault

    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    error_entity = next(
        e for e in entities
        if hasattr(e, "entity_description") and e.entity_description.key == "error_code"
    )

    assert error_entity.entity_description.is_available(mock_aquarea_device) is True
    assert error_entity.entity_description.get_state(mock_aquarea_device) == "H99"


async def test_error_code_unavailable_when_no_error(
    hass, mock_aquarea_coordinator, mock_aquarea_device
):
    mock_aquarea_device.is_on_error = False
    mock_aquarea_device.current_error = None

    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    error_entity = next(
        e for e in entities
        if hasattr(e, "entity_description") and e.entity_description.key == "error_code"
    )

    assert error_entity.entity_description.is_available(mock_aquarea_device) is False
    assert error_entity.entity_description.get_state(mock_aquarea_device) is None


async def test_pump_direction_sensor_registered(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert any(isinstance(e, AquareaPumpDirectionSensor) for e in entities)


async def test_pump_status_sensor_registered(hass, mock_aquarea_coordinator):
    entities = await _collect_entities(hass, [mock_aquarea_coordinator])
    assert any(isinstance(e, AquareaPumpStatusSensor) for e in entities)
