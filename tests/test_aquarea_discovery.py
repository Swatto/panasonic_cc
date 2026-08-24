"""Tests for how Aquarea heat pumps are discovered in the Comfort Cloud device list.

Regression coverage for the aio-panasonic-comfort-cloud 2026.6 -> 2026.8 bump:
that release taught the library to recognize Aquarea units itself, so they moved
out of `unknown_devices` and into `aquarea_devices`. The integration gated its
whole Aquarea setup on `has_unknown_devices`, so every heat pump silently
vanished from Home Assistant while air conditioners kept working.

The first half exercises the library's classification directly (no network) so
the gate the integration relies on is pinned to real library behavior; the
second half drives `async_setup_entry` to prove a recognized Aquarea unit
actually reaches a coordinator.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aio_panasonic_comfort_cloud import ApiClient

from custom_components.panasonic_cc import DOMAIN, async_setup_entry
from custom_components.panasonic_cc.const import AQUAREA_COORDINATORS


# An Aquarea unit as it appears in the /device/group listing: deviceType "2",
# no nested `parameters`, tank/zone status at the top level.
AQUAREA_RAW = {
    "deviceGuid": "AQ-GUID-1",
    "deviceName": "Aquarea",
    "deviceType": "2",
    "deviceModuleNumber": "WH-ADC0309J3E5",
    "tankStatus": [{"operationStatus": 1}],
    "zoneStatus": [{"zoneId": 1, "operationStatus": 1}],
}

# An air conditioner: deviceType "1", with a nested `parameters` object.
AC_RAW = {
    "deviceGuid": "AC-GUID-1",
    "deviceName": "Living AC",
    "deviceType": "1",
    "parameters": {"operate": 1},
}


def _api_with(*raw_devices) -> ApiClient:
    """ApiClient pre-loaded with a group listing, without touching the network."""
    api = ApiClient("user", "password", MagicMock())
    api._groups = {"groupList": [{"groupName": "Home", "deviceList": list(raw_devices)}]}
    api._devices = None
    return api


async def test_aquarea_is_classified_as_aquarea_not_unknown():
    api = _api_with(AC_RAW, AQUAREA_RAW)

    assert [d.name for d in api.get_devices()] == ["Living AC"]
    assert [d.name for d in api.aquarea_devices] == ["Aquarea"]
    # The gate that used to carry Aquarea setup no longer fires...
    assert api.has_unknown_devices is False
    # ...so the integration must key off this one instead.
    assert api.has_aquarea_devices is True


async def test_aquarea_only_account_still_reports_devices():
    """An Aquarea-only account must not be treated as an empty account."""
    api = _api_with(AQUAREA_RAW)

    assert api.get_devices() == []
    assert api.has_devices is True


async def test_empty_account_reports_no_devices():
    api = _api_with()

    assert api.has_devices is False


@pytest.mark.parametrize(
    "gate",
    ["has_devices", "has_aquarea_devices", "has_unknown_devices"],
    ids=lambda g: g,
)
async def test_gates_used_by_the_integration_exist(gate):
    """Fail loudly if a future bump renames the properties setup depends on."""
    assert isinstance(getattr(_api_with(AQUAREA_RAW), gate), bool)


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"username": "user", "password": "password", "update_interval_version": 2}
    entry.options = {}
    return entry


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    return hass


async def test_setup_creates_coordinator_for_library_recognized_aquarea():
    """A heat pump in `aquarea_devices` (and not `unknown_devices`) must still
    get an AquareaDeviceCoordinator — the exact case that broke on the bump."""
    api = MagicMock()
    api.start_session = AsyncMock()
    api.get_devices.return_value = []
    api.has_devices = True
    api.has_aquarea_devices = True
    api.has_unknown_devices = False

    aquarea_device_info = MagicMock(name="heat-pump")
    aquarea_client = MagicMock()
    aquarea_client.get_devices = AsyncMock(return_value=[aquarea_device_info])

    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()

    hass = _hass()
    with (
        patch("custom_components.panasonic_cc.ApiClient", return_value=api),
        patch("custom_components.panasonic_cc.AquareaApiClient", return_value=aquarea_client),
        patch("custom_components.panasonic_cc._aquarea_login", AsyncMock()),
        patch("custom_components.panasonic_cc._save_aquarea_token", AsyncMock()),
        patch("custom_components.panasonic_cc.async_get_clientsession", MagicMock()),
        patch(
            "custom_components.panasonic_cc.AquareaDeviceCoordinator",
            return_value=coordinator,
        ) as coordinator_cls,
    ):
        assert await async_setup_entry(hass, _entry()) is True

    coordinator_cls.assert_called_once()
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert hass.data[DOMAIN][AQUAREA_COORDINATORS] == [coordinator]


async def test_setup_skips_aquarea_when_account_has_none():
    """AC-only accounts must not pay for an Aquarea login."""
    api = MagicMock()
    api.start_session = AsyncMock()
    api.get_devices.return_value = []
    api.has_devices = True
    api.has_aquarea_devices = False
    api.has_unknown_devices = False

    hass = _hass()
    with (
        patch("custom_components.panasonic_cc.ApiClient", return_value=api),
        patch("custom_components.panasonic_cc.AquareaApiClient") as aquarea_client_cls,
        patch("custom_components.panasonic_cc._aquarea_login", AsyncMock()) as login,
        patch("custom_components.panasonic_cc.async_get_clientsession", MagicMock()),
    ):
        assert await async_setup_entry(hass, _entry()) is True

    aquarea_client_cls.assert_not_called()
    login.assert_not_awaited()
    assert hass.data[DOMAIN][AQUAREA_COORDINATORS] == []
