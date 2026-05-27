"""Platform for the Panasonic Comfort Cloud."""

import datetime as dt
import logging
from typing import Any

import asyncio

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from aio_panasonic_comfort_cloud import ApiClient
from aioaquarea import Client as AquareaApiClient

_AQUAREA_TOKEN_STORE_VERSION = 1

from .const import (
    CONF_UPDATE_INTERVAL_VERSION,
    CONF_ENABLE_DAILY_ENERGY_SENSOR,
    CONF_DEVICE_FETCH_INTERVAL,
    CONF_ENERGY_FETCH_INTERVAL,
    DEFAULT_DEVICE_FETCH_INTERVAL,
    DEFAULT_ENERGY_FETCH_INTERVAL,
    DEFAULT_ENABLE_DAILY_ENERGY_SENSOR,
    CONF_USE_PANASONIC_PRESET_NAMES,
    PANASONIC_DEVICES,
    COMPONENT_TYPES,
    STARTUP,
    DATA_COORDINATORS,
    ENERGY_COORDINATORS,
    AQUAREA_COORDINATORS,
)

from .coordinator import (
    PanasonicDeviceCoordinator,
    PanasonicDeviceEnergyCoordinator,
    AquareaDeviceCoordinator,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "panasonic_cc"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(
                    CONF_ENABLE_DAILY_ENERGY_SENSOR,
                    default=DEFAULT_ENABLE_DAILY_ENERGY_SENSOR,
                ): cv.boolean,
                # noqa: E501
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

def _aquarea_token_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, _AQUAREA_TOKEN_STORE_VERSION, f"panasonic_cc_aquarea_token_{entry_id}")


async def _save_aquarea_token(hass: HomeAssistant, entry_id: str, client: AquareaApiClient) -> None:
    """Persist Aquarea auth token to HA storage so it survives restarts."""
    s = client._settings
    if not s.access_token:
        return
    await _aquarea_token_store(hass, entry_id).async_save({
        "access_token": s.access_token,
        "refresh_token": s.refresh_token,
        "expires_at": s.expires_at,
        "scope": s.scope,
        "client_id": s.clientId,
    })


async def _aquarea_login(hass: HomeAssistant, entry_id: str, client: AquareaApiClient) -> None:
    """Login to Aquarea, trying stored token → refresh → full login in that order."""
    stored = await _aquarea_token_store(hass, entry_id).async_load()

    if stored and stored.get("access_token"):
        # Restore token into the client so is_logged works correctly
        client._settings.set_token(
            stored["access_token"],
            stored.get("refresh_token"),
            stored.get("expires_at"),
            stored.get("scope"),
        )
        if stored.get("client_id"):
            client._settings.clientId = stored["client_id"]
        client._api_client.access_token = stored["access_token"]
        if stored.get("expires_at"):
            client._api_client.token_expiration = dt.datetime.fromtimestamp(
                stored["expires_at"], tz=dt.timezone.utc
            )

        if client.is_logged:
            _LOGGER.debug("Aquarea: stored token still valid, skipping full login")
            await client._app_version.init()
            client._last_login = dt.datetime.now()
            await _save_aquarea_token(hass, entry_id, client)
            return

        # Token expired — try cheap refresh before full OAuth
        if stored.get("refresh_token") and stored.get("scope"):
            try:
                _LOGGER.debug("Aquarea: stored token expired, attempting token refresh")
                await client._app_version.init()
                await client._authenticator.refresh_token()
                await client._authenticator._retrieve_client_acc()
                client._api_client.access_token = client._settings.access_token
                if client._settings.expires_at:
                    client._api_client.token_expiration = dt.datetime.fromtimestamp(
                        client._settings.expires_at, tz=dt.timezone.utc
                    )
                client._last_login = dt.datetime.now()
                _LOGGER.debug("Aquarea: token refreshed successfully")
                await _save_aquarea_token(hass, entry_id, client)
                return
            except Exception as err:
                _LOGGER.warning("Aquarea: token refresh failed (%s), falling back to full login", err)

    _LOGGER.debug("Aquarea: performing full login")
    await client.login()
    await _save_aquarea_token(hass, entry_id, client)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Panasonic Comfort Cloud component."""

    hass.data.setdefault(DOMAIN, {})
    integration = await async_get_integration(hass, DOMAIN)

    _LOGGER.info(STARTUP, integration.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Establish connection with Comfort Cloud."""

    conf = dict(entry.data)
    username = conf[CONF_USERNAME]
    password = conf[CONF_PASSWORD]
    enable_daily_energy_sensor = entry.options.get(
        CONF_ENABLE_DAILY_ENERGY_SENSOR, DEFAULT_ENABLE_DAILY_ENERGY_SENSOR
    )

    client = async_get_clientsession(hass)
    api = ApiClient(username, password, client)
    await api.start_session()
    devices = api.get_devices()

    if (
        CONF_UPDATE_INTERVAL_VERSION not in conf
        or conf[CONF_UPDATE_INTERVAL_VERSION] < 2
    ):
        _LOGGER.info("Updating configuration")
        updated_config = dict(entry.data)
        updated_config[CONF_UPDATE_INTERVAL_VERSION] = 2
        if (
            CONF_DEVICE_FETCH_INTERVAL not in conf
            or conf[CONF_DEVICE_FETCH_INTERVAL] <= 31
        ):
            updated_config[CONF_DEVICE_FETCH_INTERVAL] = DEFAULT_DEVICE_FETCH_INTERVAL
            _LOGGER.info(
                f"Setting default fetch interval to {DEFAULT_DEVICE_FETCH_INTERVAL}"
            )
        if (
            CONF_ENERGY_FETCH_INTERVAL not in conf
            or conf[CONF_ENERGY_FETCH_INTERVAL] <= 61
        ):
            updated_config[CONF_ENERGY_FETCH_INTERVAL] = DEFAULT_ENERGY_FETCH_INTERVAL
            _LOGGER.info(
                f"Setting default energy fetch interval to {DEFAULT_ENERGY_FETCH_INTERVAL}"
            )
        hass.config_entries.async_update_entry(entry, data=updated_config)
        conf = dict(entry.data)

    if len(devices) == 0 and not api.has_unknown_devices:
        _LOGGER.error("Could not find any Panasonic Comfort Cloud Heat Pumps")
        return False

    _LOGGER.info("Got %s devices", len(devices))
    data_coordinators: list[PanasonicDeviceCoordinator] = []
    energy_coordinators: list[PanasonicDeviceEnergyCoordinator] = []
    aquarea_coordinators: list[AquareaDeviceCoordinator] = []

    for device in devices:
        try:
            device_coordinator = PanasonicDeviceCoordinator(hass, conf, api, device)
            await device_coordinator.async_config_entry_first_refresh()
            data_coordinators.append(device_coordinator)
            if enable_daily_energy_sensor:
                energy_coordinators.append(
                    PanasonicDeviceEnergyCoordinator(hass, conf, api, device)
                )
        except Exception as e:
            _LOGGER.warning(f"Failed to setup device: {device.name} ({e})", exc_info=e)

    if api.has_unknown_devices:
        try:
            aquarea_api_client = AquareaApiClient(client, username, password)
            await _aquarea_login(hass, entry.entry_id, aquarea_api_client)
            aquarea_devices = await aquarea_api_client.get_devices()
            for aquarea_device in aquarea_devices:
                try:
                    async def _save_token() -> None:
                        await _save_aquarea_token(hass, entry.entry_id, aquarea_api_client)

                    aquarea_device_coordinator = AquareaDeviceCoordinator(
                        hass, conf, aquarea_api_client, aquarea_device,
                        on_token_saved=_save_token,
                    )
                    await aquarea_device_coordinator.async_config_entry_first_refresh()
                    aquarea_coordinators.append(aquarea_device_coordinator)
                except ConfigEntryNotReady:
                    raise
                except Exception as e:
                    _LOGGER.warning(
                        f"Failed to setup Aquarea device: {aquarea_device.name} ({e})",
                        exc_info=e,
                    )
        except ConfigEntryNotReady:
            raise
        except Exception as e:
            _LOGGER.warning(f"Failed to setup Aquarea: {e}", exc_info=e)

    hass.data[DOMAIN][DATA_COORDINATORS] = data_coordinators
    hass.data[DOMAIN][ENERGY_COORDINATORS] = energy_coordinators
    hass.data[DOMAIN][AQUAREA_COORDINATORS] = aquarea_coordinators
    energy_results = await asyncio.gather(
        *(data.async_config_entry_first_refresh() for data in energy_coordinators),
        return_exceptions=True,
    )
    for idx, result in enumerate(energy_results):
        if isinstance(result, Exception):
            _LOGGER.warning(
                "Energy coordinator %d first refresh failed: %s", idx, result
            )

    await hass.config_entries.async_forward_entry_setups(entry, COMPONENT_TYPES)
    return True


async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, COMPONENT_TYPES)
