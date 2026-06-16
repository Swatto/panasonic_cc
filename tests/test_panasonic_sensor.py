"""Tests for Panasonic Comfort Cloud (non-Aquarea) sensor registration.

Focus: the outside-temperature sensor gate in sensor.async_setup_entry, which
now also honours the CONF_FORCE_OUTSIDE_SENSOR option (read from entry.options).
"""

from unittest.mock import MagicMock

import pytest

from custom_components.panasonic_cc import sensor
from custom_components.panasonic_cc.const import (
    AQUAREA_COORDINATORS,
    CONF_FORCE_OUTSIDE_SENSOR,
    DATA_COORDINATORS,
    DOMAIN,
    ENERGY_COORDINATORS,
)


def _make_cc_coordinator(outside_temperature):
    """Mock a PanasonicDeviceCoordinator with the given outside temperature."""
    coordinator = MagicMock()
    coordinator.device_id = "test-cc-device"
    coordinator.device_info = MagicMock()
    device = coordinator.device
    device.has_zones = False
    device.parameters.inside_temperature = 21.0
    device.parameters.outside_temperature = outside_temperature
    return coordinator


def _setup_hass(hass, data_coordinators):
    hass.data[DOMAIN] = {
        DATA_COORDINATORS: data_coordinators,
        ENERGY_COORDINATORS: [],
        AQUAREA_COORDINATORS: [],
    }


async def _collect_entities(hass, data_coordinators, options):
    entities = []
    _setup_hass(hass, data_coordinators)
    entry = MagicMock()
    entry.options = options
    await sensor.async_setup_entry(hass, entry, lambda e, **kw: entities.extend(e))
    return entities


def _keys(entities):
    keys = set()
    for e in entities:
        desc = getattr(e, "entity_description", None)
        if desc is not None and getattr(desc, "key", None) is not None:
            keys.add(desc.key)
    return keys


async def test_outside_sensor_skipped_when_no_value_and_not_forced(hass):
    coordinator = _make_cc_coordinator(outside_temperature=None)
    entities = await _collect_entities(hass, [coordinator], options={})
    assert "outside_temperature" not in _keys(entities)
    # Sanity: the inside-temperature sensor is always registered.
    assert "inside_temperature" in _keys(entities)


async def test_outside_sensor_registered_when_value_available(hass):
    coordinator = _make_cc_coordinator(outside_temperature=12.5)
    entities = await _collect_entities(hass, [coordinator], options={})
    assert "outside_temperature" in _keys(entities)


async def test_outside_sensor_forced_when_no_value(hass):
    coordinator = _make_cc_coordinator(outside_temperature=None)
    entities = await _collect_entities(
        hass, [coordinator], options={CONF_FORCE_OUTSIDE_SENSOR: True}
    )
    assert "outside_temperature" in _keys(entities)


async def test_force_flag_false_behaves_like_default(hass):
    coordinator = _make_cc_coordinator(outside_temperature=None)
    entities = await _collect_entities(
        hass, [coordinator], options={CONF_FORCE_OUTSIDE_SENSOR: False}
    )
    assert "outside_temperature" not in _keys(entities)
