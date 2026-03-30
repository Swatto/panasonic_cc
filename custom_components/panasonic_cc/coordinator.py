import asyncio
import logging

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from aio_panasonic_comfort_cloud import (
    ApiClient,
    PanasonicDevice,
    PanasonicDeviceInfo,
    PanasonicDeviceEnergy,
    ChangeRequestBuilder,
)
from aioaquarea import (
    Client as AquareaApiClient,
    Device as AquareaDevice,
)
from aioaquarea.data import DeviceInfo as AquareaDeviceInfo
from aioaquarea.errors import AuthenticationError, RequestFailedError, ApiError, ClientError
from aioaquarea.statistics import DateType
from .const import (
    DOMAIN,
    MANUFACTURER,
    DEFAULT_DEVICE_FETCH_INTERVAL,
    CONF_DEVICE_FETCH_INTERVAL,
    CONF_ENERGY_FETCH_INTERVAL,
    DEFAULT_ENERGY_FETCH_INTERVAL,
    DEFAULT_DAILY_CONSUMPTION_INTERVAL,
    CONF_CONSUMPTION_INTERVAL,
    DEFAULT_CONSUMPTION_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class PanasonicDeviceCoordinator(DataUpdateCoordinator[int]):

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        api_client: ApiClient,
        device_info: PanasonicDeviceInfo,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="Panasonic Device Coordinator",
            update_interval=timedelta(
                seconds=config.get(
                    CONF_DEVICE_FETCH_INTERVAL, DEFAULT_DEVICE_FETCH_INTERVAL
                )
            ),
            update_method=self._fetch_device_data,
        )
        self._hass = hass
        self._config = config
        self._api_client = api_client
        self._panasonic_device_info = device_info
        self._device: PanasonicDevice | None = None
        self._store = Store(hass, version=1, key=f"panasonic_cc_{device_info.id}")
        self._update_id = 0

    @property
    def device(self) -> PanasonicDevice:
        if self._device is None:
            raise ValueError("device has not been initialized")
        return self._device

    @property
    def api_client(self) -> ApiClient:
        return self._api_client

    @property
    def device_id(self) -> str:
        return self._panasonic_device_info.id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._panasonic_device_info.id)},
            manufacturer=MANUFACTURER,
            model=self._panasonic_device_info.model,
            name=self._panasonic_device_info.name,
            sw_version=self._api_client.app_version,
        )

    def get_change_request_builder(self):
        return ChangeRequestBuilder(self.device)

    async def async_apply_changes(self, request_builder: ChangeRequestBuilder):
        await self._api_client.set_device_raw(self.device, request_builder.build())

    async def async_get_stored_data(self):
        data = await self._store.async_load()
        if data is None:
            data = {}
        return data

    async def async_store_data(self, data):
        await self._store.async_save(data)

    async def _fetch_device_data(self) -> int:
        try:
            if self._device is None:
                self._device = await self._api_client.get_device(
                    self._panasonic_device_info
                )
                _LOGGER.debug(
                    "%s Device features\nNanoe: %s\nEco Navi: %s\nAI Eco: %s",
                    self._panasonic_device_info.name,
                    self._device.has_nanoe,
                    self._device.has_eco_navi,
                    self._device.has_eco_function,
                )
                self._update_id = 1
                return self._update_id
            if await self._api_client.try_update_device(self._device):
                self._update_id = self._update_id + 1
                return self._update_id
        except BaseException as e:
            _LOGGER.error("Error fetching device data from API: %s", e, exc_info=e)
            raise UpdateFailed(f"Invalid response from API: {e}") from e
        return self._update_id


class PanasonicDeviceEnergyCoordinator(DataUpdateCoordinator[int]):

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        api_client: ApiClient,
        device_info: PanasonicDeviceInfo,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="Panasonic Device Energy Coordinator",
            update_interval=timedelta(
                seconds=config.get(
                    CONF_ENERGY_FETCH_INTERVAL, DEFAULT_ENERGY_FETCH_INTERVAL
                )
            ),
            update_method=self._fetch_device_data,
        )
        self._hass = hass
        self._config = config
        self._api_client = api_client
        self._panasonic_device_info = device_info
        self._energy: PanasonicDeviceEnergy | None = None
        self._update_id = 0

    @property
    def api_client(self) -> ApiClient:
        return self._api_client

    @property
    def device_id(self) -> str:
        return self._panasonic_device_info.id

    @property
    def energy(self) -> PanasonicDeviceEnergy | None:
        return self._energy

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._panasonic_device_info.id)},
            manufacturer=MANUFACTURER,
            model=self._panasonic_device_info.model,
            name=self._panasonic_device_info.name,
            sw_version=self._api_client.app_version,
        )

    async def _fetch_device_data(self) -> int:
        try:
            if self._energy is None:
                self._energy = await self._api_client.async_get_energy(
                    self._panasonic_device_info
                )
                self._update_id = 1
                return self._update_id
            if await self._api_client.async_try_update_energy(self._energy):
                self._update_id = self._update_id + 1
                return self._update_id
        except BaseException as e:
            _LOGGER.error("Error fetching energy data from API: %s", e, exc_info=e)
            raise UpdateFailed(f"Invalid response from API: {e}") from e
        return self._update_id


class AquareaDeviceCoordinator(DataUpdateCoordinator):

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        api_client: AquareaApiClient,
        device_info: AquareaDeviceInfo,
        on_token_saved: Callable[[], Awaitable[None]] | None = None,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name="Aquarea Device Coordinator",
            update_interval=timedelta(
                seconds=config.get(
                    CONF_DEVICE_FETCH_INTERVAL, DEFAULT_DEVICE_FETCH_INTERVAL
                )
            ),
            update_method=self._fetch_device_data,
        )
        self._hass = hass
        self._config = config
        self._api_client = api_client
        self._aquarea_device_info = device_info
        self._device: AquareaDevice | None = None
        self._update_id = 0
        self._on_token_saved = on_token_saved

        # Consumption caching
        self._day_consumption = None
        self._month_consumption = None
        self._last_daily_fetch_time: datetime | None = None
        self._last_monthly_fetch_time: datetime | None = None
        self._consumption_interval = config.get(
            CONF_CONSUMPTION_INTERVAL, DEFAULT_CONSUMPTION_INTERVAL
        )

    @property
    def device(self) -> AquareaDevice:
        if self._device is None:
            raise ValueError("device has not been initialized")
        return self._device

    @property
    def api_client(self) -> AquareaApiClient:
        return self._api_client

    @property
    def device_id(self) -> str:
        if self._device is not None:
            # Buscar id, device_id, guid, long_id
            for attr in ("device_id", "id", "guid", "long_id"):
                val = getattr(self._device, attr, None)
                if val:
                    return str(val)
        return self._aquarea_device_info.id

    @property
    def device_info(self) -> DeviceInfo:
        # Acceso seguro a nombre
        name = (
            getattr(self._device, "display_name", None)
            or getattr(self._device, "nickname", None)
            or getattr(self._device, "device_name", None)
            or getattr(self._device, "name", None)
            or self._aquarea_device_info.name
        )
        if not name or name == "N/A" or name == "Unknown":
            name = "Aquarea Device"
            
        manufacturer = getattr(self._device, "manufacturer", None) or "Panasonic"
        model = getattr(self._device, "model", None) or getattr(self._aquarea_device_info, "model", "")
        # Acceso seguro a versión
        sw_version = (
            getattr(self._device, "firmware_version", None)
            or getattr(self._device, "version", None)
            or getattr(self._aquarea_device_info, "firmware_version", None)
        )
        if not sw_version or sw_version == "N/A" or sw_version == "Unknown":
            sw_version = "Unknown"
            
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            manufacturer=manufacturer,
            model=model,
            name=name,
            sw_version=sw_version,
        )

    async def async_request_refresh(self, force_fetch: bool = False) -> None:
        """Request a refresh, optionally forcing a full re-fetch."""
        if force_fetch:
            self._device = None
        await super().async_request_refresh()

    @property
    def day_consumption(self):
        """Return the last cached day (hourly) consumption entries."""
        return self._day_consumption

    @property
    def month_consumption(self):
        """Return the last cached month consumption entries."""
        return self._month_consumption

    async def _fetch_device_data(self) -> int:
        for attempt in (1, 2):
            try:
                if self._device is None:
                    self._device = await self._api_client.get_device(
                        device_info=self._aquarea_device_info,
                        consumption_refresh_interval=timedelta(
                            seconds=self._config.get(
                                CONF_ENERGY_FETCH_INTERVAL,
                                DEFAULT_ENERGY_FETCH_INTERVAL,
                            )
                        ),
                        timezone=dt_util.DEFAULT_TIME_ZONE,
                    )
                    self._update_id = 1
                else:
                    await self._device.refresh_data()
                    self._update_id = self._update_id + 1

                # Fetch consumption data with tiered intervals
                await self._fetch_consumption_data()

                return self._update_id

            except (AuthenticationError, RequestFailedError, ClientError, ApiError) as err:
                if attempt == 2:
                    _LOGGER.error(
                        "Aquarea fetch failed after retry: %s",
                        err,
                    )
                    raise UpdateFailed(
                        f"Invalid response from API: {err}"
                    ) from err

                error_str = str(err).lower()
                cause_is_auth = isinstance(err.__cause__, AuthenticationError)
                if isinstance(err, AuthenticationError) or cause_is_auth or "token" in error_str or "auth" in error_str:
                    _LOGGER.warning(
                        "Aquarea token expired or auth error, re-authenticating and retrying once"
                    )
                    await self._api_client.login()
                    self._device = None
                    if self._on_token_saved:
                        await self._on_token_saved()
                    continue

                if isinstance(err, ApiError) and "failed communication with adaptor" in error_str:
                    _LOGGER.warning("Panasonic Cloud cannot communicate with the Aquarea WiFi module. It may be offline.")
                    raise UpdateFailed("Adaptor offline or unreachable") from err

                _LOGGER.warning(
                    "Aquarea request failed: %s, re-authenticating and retrying", err
                )
                await self._api_client.login()
                self._device = None
                if self._on_token_saved:
                    await self._on_token_saved()

            except BaseException as e:
                _LOGGER.error("Unexpected error fetching device data from API: %s", e, exc_info=e)
                raise UpdateFailed(f"Invalid response from API: {e}") from e

        return self._update_id

    async def _fetch_consumption_data(self) -> None:
        """Fetch daily and monthly consumption data with tiered intervals."""
        if self._device is None:
            return

        now = dt_util.now()
        fetch_daily = (
            self._last_daily_fetch_time is None
            or (now - self._last_daily_fetch_time) >= timedelta(minutes=DEFAULT_DAILY_CONSUMPTION_INTERVAL)
        )
        fetch_monthly = (
            self._last_monthly_fetch_time is None
            or (now - self._last_monthly_fetch_time) >= timedelta(minutes=self._consumption_interval)
        )

        if not fetch_daily and not fetch_monthly:
            return

        tasks = []
        if fetch_daily:
            previous_hour = now - timedelta(hours=1)
            date_str = previous_hour.strftime("%Y%m%d")
            tasks.append(self._api_client.get_device_consumption(
                self._device.long_id, DateType.DAY, date_str
            ))
        else:
            tasks.append(asyncio.sleep(0, result=self._day_consumption))

        if fetch_monthly:
            month_date_str = now.strftime("%Y%m01")
            tasks.append(self._api_client.get_device_consumption(
                self._device.long_id, DateType.MONTH, month_date_str
            ))
        else:
            tasks.append(asyncio.sleep(0, result=self._month_consumption))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        if fetch_daily:
            if isinstance(results[0], Exception):
                _LOGGER.warning("Failed to fetch day consumption: %s", results[0])
            else:
                self._day_consumption = results[0]
                self._last_daily_fetch_time = now

        if fetch_monthly:
            if isinstance(results[1], Exception):
                _LOGGER.warning("Failed to fetch month consumption: %s", results[1])
            else:
                self._month_consumption = results[1]
                self._last_monthly_fetch_time = now
