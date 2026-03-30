"""Tests for Aquarea select write operations.

Verifies that async_select_option calls the correct device methods
and optimistic state works correctly.
"""

from unittest.mock import AsyncMock, MagicMock

import aioaquarea
import pytest

from custom_components.panasonic_cc import select
from custom_components.panasonic_cc.select import (
    AquareaQuietModeSelect,
    AquareaPowerfulTimeSelect,
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


async def _collect_selects(hass, coordinators):
    entities = []
    _setup_hass(hass, coordinators)
    await select.async_setup_entry(hass, MagicMock(), lambda e, **kw: entities.extend(e))
    return entities


def _patch_entity(entity, hass):
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()


async def test_quiet_mode_select_option_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_quiet_mode = AsyncMock()
    mock_aquarea_device.quiet_mode = aioaquarea.QuietMode.OFF
    hass.async_create_task = MagicMock()
    entities = await _collect_selects(hass, [mock_aquarea_coordinator])
    qm = next(e for e in entities if isinstance(e, AquareaQuietModeSelect))
    _patch_entity(qm, hass)

    await qm.async_select_option("level2")

    mock_aquarea_device.set_quiet_mode.assert_called_once_with(aioaquarea.QuietMode.LEVEL2)
    assert qm._optimistic_option == "level2"
    hass.async_create_task.assert_called_once()


async def test_quiet_mode_skips_if_same(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_quiet_mode = AsyncMock()
    mock_aquarea_device.quiet_mode = aioaquarea.QuietMode.LEVEL1
    hass.async_create_task = MagicMock()
    entities = await _collect_selects(hass, [mock_aquarea_coordinator])
    qm = next(e for e in entities if isinstance(e, AquareaQuietModeSelect))
    _patch_entity(qm, hass)

    await qm.async_select_option("level1")

    mock_aquarea_device.set_quiet_mode.assert_not_called()


async def test_powerful_time_select_option_calls_device(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.set_powerful_time = AsyncMock()
    mock_aquarea_device.powerful_time = aioaquarea.PowerfulTime.OFF
    hass.async_create_task = MagicMock()
    entities = await _collect_selects(hass, [mock_aquarea_coordinator])
    pt = next(e for e in entities if isinstance(e, AquareaPowerfulTimeSelect))
    _patch_entity(pt, hass)

    await pt.async_select_option("on-60m")

    mock_aquarea_device.set_powerful_time.assert_called_once_with(aioaquarea.PowerfulTime.ON_60MIN)
    assert pt._optimistic_option == "on-60m"


async def test_powerful_time_icon_changes(hass, mock_aquarea_coordinator, mock_aquarea_device):
    mock_aquarea_device.powerful_time = aioaquarea.PowerfulTime.OFF
    entities = await _collect_selects(hass, [mock_aquarea_coordinator])
    pt = next(e for e in entities if isinstance(e, AquareaPowerfulTimeSelect))

    assert pt.icon == "mdi:fire-off"

    mock_aquarea_device.powerful_time = aioaquarea.PowerfulTime.ON_30MIN
    assert pt.icon == "mdi:fire"
