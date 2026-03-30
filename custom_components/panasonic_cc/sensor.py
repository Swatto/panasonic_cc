from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, Self

from homeassistant.const import UnitOfTemperature, UnitOfEnergy, EntityCategory
from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorExtraStoredData,
)
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

import aioaquarea
from aio_panasonic_comfort_cloud import (
    PanasonicDevice,
    PanasonicDeviceEnergy,
    PanasonicDeviceZone,
    constants,
)
from aioaquarea import Device as AquareaDevice

from .const import DOMAIN, DATA_COORDINATORS, ENERGY_COORDINATORS, AQUAREA_COORDINATORS
from .base import PanasonicDataEntity, PanasonicEnergyEntity, AquareaDataEntity
from .coordinator import (
    PanasonicDeviceCoordinator,
    PanasonicDeviceEnergyCoordinator,
    AquareaDeviceCoordinator,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PanasonicSensorEntityDescription(SensorEntityDescription):
    """Describes Panasonic sensor entity."""

    get_state: Callable[[PanasonicDevice], Any] | None = None
    is_available: Callable[[PanasonicDevice], bool] | None = None


@dataclass(frozen=True, kw_only=True)
class PanasonicEnergySensorEntityDescription(SensorEntityDescription):
    """Describes Panasonic sensor entity."""

    get_state: Callable[[PanasonicDeviceEnergy], Any] | None = None


@dataclass(frozen=True, kw_only=True)
class AquareaSensorEntityDescription(SensorEntityDescription):
    """Describes Aquarea sensor entity."""

    get_state: Callable[[AquareaDevice], Any] | None = None
    is_available: Callable[[AquareaDevice], bool] | None = None


INSIDE_TEMPERATURE_DESCRIPTION = PanasonicSensorEntityDescription(
    key="inside_temperature",
    translation_key="inside_temperature",
    name="Inside Temperature",
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    get_state=lambda device: device.parameters.inside_temperature,
    is_available=lambda device: device.parameters.inside_temperature is not None,
)
OUTSIDE_TEMPERATURE_DESCRIPTION = PanasonicSensorEntityDescription(
    key="outside_temperature",
    translation_key="outside_temperature",
    name="Outside Temperature",
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    get_state=lambda device: device.parameters.outside_temperature,
    is_available=lambda device: device.parameters.outside_temperature is not None,
)
LAST_UPDATE_TIME_DESCRIPTION = PanasonicSensorEntityDescription(
    key="last_update",
    translation_key="last_update",
    name="Last Updated",
    icon="mdi:clock-outline",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=None,
    native_unit_of_measurement=None,
    get_state=lambda device: device.last_update,
    is_available=lambda device: True,
    entity_registry_enabled_default=False,
)
DATA_AGE_DESCRIPTION = PanasonicSensorEntityDescription(
    key="data_age",
    translation_key="data_age",
    name="Cached Data Age",
    icon="mdi:clock-outline",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=None,
    native_unit_of_measurement=None,
    get_state=lambda device: device.timestamp,
    is_available=lambda device: device.info.status_data_mode
    == constants.StatusDataMode.CACHED,
    entity_registry_enabled_default=False,
)
DATA_MODE_DESCRIPTION = PanasonicSensorEntityDescription(
    key="status_data_mode",
    translation_key="status_data_mode",
    name="Data Mode",
    options=[opt.name for opt in constants.StatusDataMode],
    device_class=SensorDeviceClass.ENUM,
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=None,
    native_unit_of_measurement=None,
    get_state=lambda device: device.info.status_data_mode.name,
    is_available=lambda device: True,
    entity_registry_enabled_default=True,
)
DAILY_ENERGY_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="daily_energy_sensor",
    translation_key="daily_energy_sensor",
    name="Daily Energy",
    icon="mdi:flash",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement="kWh",
    get_state=lambda energy: energy.consumption,
)
DAILY_HEATING_ENERGY_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="daily_heating_energy",
    translation_key="daily_heating_energy",
    name="Daily Heating Energy",
    icon="mdi:flash",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement="kWh",
    get_state=lambda energy: energy.heating_consumption,
)
DAILY_COOLING_ENERGY_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="daily_cooling_energy",
    translation_key="daily_cooling_energy",
    name="Daily Cooling Energy",
    icon="mdi:flash",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement="kWh",
    get_state=lambda energy: energy.cooling_consumption,
)
POWER_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="current_power",
    translation_key="current_power",
    name="Current Extrapolated Power",
    icon="mdi:flash",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="W",
    get_state=lambda energy: energy.current_power,
)
COOLING_POWER_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="cooling_power",
    translation_key="cooling_power",
    name="Cooling Extrapolated Power",
    icon="mdi:flash",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="W",
    get_state=lambda energy: energy.cooling_power,
)
HEATING_POWER_DESCRIPTION = PanasonicEnergySensorEntityDescription(
    key="heating_power",
    translation_key="heating_power",
    name="Heating Extrapolated Power",
    icon="mdi:flash",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="W",
    get_state=lambda energy: energy.heating_power,
)

AQUAREA_OUTSIDE_TEMPERATURE_DESCRIPTION = AquareaSensorEntityDescription(
    key="outside_temperature",
    translation_key="outside_temperature",
    name="Outside Temperature",
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    get_state=lambda device: device.temperature_outdoor,
    is_available=lambda device: device.temperature_outdoor is not None,
)


@dataclass(frozen=True, kw_only=True)
class AquareaEnergyConsumptionSensorDescription(SensorEntityDescription):
    consumption_type: aioaquarea.ConsumptionType
    exists_fn: Callable[[AquareaDeviceCoordinator], bool] = lambda _: True


ACCUMULATED_ENERGY_SENSORS = [
    AquareaEnergyConsumptionSensorDescription(
        key="heating_accumulated_energy_consumption",
        translation_key="heating_accumulated_energy_consumption",
        name="Heating Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.HEAT,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="cooling_accumulated_energy_consumption",
        translation_key="cooling_accumulated_energy_consumption",
        name="Cooling Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.COOL,
        exists_fn=lambda coord: any(
            zone.cool_mode for zone in coord.device.zones.values()
        ),
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="tank_accumulated_energy_consumption",
        translation_key="tank_accumulated_energy_consumption",
        name="Tank Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.WATER_TANK,
        exists_fn=lambda coord: coord.device.has_tank,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="accumulated_energy_consumption",
        translation_key="accumulated_energy_consumption",
        name="Accumulated Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.TOTAL,
    ),
]

ENERGY_SENSORS = [
    AquareaEnergyConsumptionSensorDescription(
        key="heating_energy_consumption",
        translation_key="heating_energy_consumption",
        name="Heating Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.HEAT,
        entity_registry_enabled_default=False,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="tank_energy_consumption",
        translation_key="tank_energy_consumption",
        name="Tank Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.WATER_TANK,
        exists_fn=lambda coord: coord.device.has_tank,
        entity_registry_enabled_default=False,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="cooling_energy_consumption",
        translation_key="cooling_energy_consumption",
        name="Cooling Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.COOL,
        exists_fn=lambda coord: any(
            zone.cool_mode for zone in coord.device.zones.values()
        ),
        entity_registry_enabled_default=False,
    ),
    AquareaEnergyConsumptionSensorDescription(
        key="energy_consumption",
        translation_key="energy_consumption",
        name="Consumption",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        consumption_type=aioaquarea.ConsumptionType.TOTAL,
        entity_registry_enabled_default=False,
    ),
]


def create_zone_temperature_description(zone: PanasonicDeviceZone):
    return PanasonicSensorEntityDescription(
        key=f"zone-{zone.id}-temperature",
        translation_key=f"zone-{zone.id}-temperature",
        name=f"{zone.name} Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        get_state=lambda device: zone.temperature,
        is_available=lambda device: zone.has_temperature,
    )


async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    data_coordinators: list[PanasonicDeviceCoordinator] = hass.data[DOMAIN][
        DATA_COORDINATORS
    ]
    energy_coordinators: list[PanasonicDeviceEnergyCoordinator] = hass.data[DOMAIN][
        ENERGY_COORDINATORS
    ]
    aquarea_coordinators: list[AquareaDeviceCoordinator] = hass.data[DOMAIN][
        AQUAREA_COORDINATORS
    ]

    for coordinator in data_coordinators:
        entities.append(
            PanasonicSensorEntity(coordinator, INSIDE_TEMPERATURE_DESCRIPTION)
        )
        if coordinator.device.parameters.outside_temperature is not None:
            entities.append(
                PanasonicSensorEntity(coordinator, OUTSIDE_TEMPERATURE_DESCRIPTION)
            )
        entities.append(
            PanasonicSensorEntity(coordinator, LAST_UPDATE_TIME_DESCRIPTION)
        )
        entities.append(PanasonicSensorEntity(coordinator, DATA_AGE_DESCRIPTION))
        entities.append(PanasonicSensorEntity(coordinator, DATA_MODE_DESCRIPTION))
        if coordinator.device.has_zones:
            for zone in coordinator.device.parameters.zones:
                entities.append(
                    PanasonicSensorEntity(
                        coordinator, create_zone_temperature_description(zone)
                    )
                )

    for coordinator in energy_coordinators:
        entities.append(
            PanasonicEnergySensorEntity(coordinator, DAILY_ENERGY_DESCRIPTION)
        )
        entities.append(
            PanasonicEnergySensorEntity(coordinator, DAILY_COOLING_ENERGY_DESCRIPTION)
        )
        entities.append(
            PanasonicEnergySensorEntity(coordinator, DAILY_HEATING_ENERGY_DESCRIPTION)
        )
        entities.append(PanasonicEnergySensorEntity(coordinator, POWER_DESCRIPTION))
        entities.append(
            PanasonicEnergySensorEntity(coordinator, COOLING_POWER_DESCRIPTION)
        )
        entities.append(
            PanasonicEnergySensorEntity(coordinator, HEATING_POWER_DESCRIPTION)
        )


    for coordinator in aquarea_coordinators:
        device = coordinator.device
        # Temperature sensors (description-based)
        entities.append(AquareaSensorEntity(coordinator, AQUAREA_OUTSIDE_TEMPERATURE_DESCRIPTION))
        if device.has_tank and device.tank is not None:
            tank_temp_desc = AquareaSensorEntityDescription(
                key="tank_temperature",
                translation_key="tank_temperature",
                name="Tank Temperature",
                icon="mdi:water-boiler",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                get_state=lambda dev: dev.tank.temperature if dev.tank else None,
                is_available=lambda dev: dev.has_tank and dev.tank is not None,
            )
            entities.append(AquareaSensorEntity(coordinator, tank_temp_desc))
        for zone in device.zones.values():
            if zone.heat_max is None:
                # Zone appears in device listing but has no live status data — skip.
                continue
            zone_temp_desc = AquareaSensorEntityDescription(
                key=f"zone_{zone.zone_id}_temperature",
                translation_key="zone_temperature",
                name=f"{zone.name} Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                get_state=lambda dev, zid=zone.zone_id: dev.zones[zid].temperature if zid in dev.zones else None,
                is_available=lambda dev, zid=zone.zone_id: zid in dev.zones,
            )
            entities.append(AquareaSensorEntity(coordinator, zone_temp_desc))
        if hasattr(device, "flow_temperature"):
            flow_temp_desc = AquareaSensorEntityDescription(
                key="flow_temperature",
                translation_key="flow_temperature",
                name="Flow Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                get_state=lambda dev: getattr(dev, "flow_temperature", None),
                is_available=lambda dev: getattr(dev, "flow_temperature", None) is not None,
            )
            entities.append(AquareaSensorEntity(coordinator, flow_temp_desc))
        if hasattr(device, "return_temperature"):
            return_temp_desc = AquareaSensorEntityDescription(
                key="return_temperature",
                translation_key="return_temperature",
                name="Return Temperature",
                icon="mdi:thermometer",
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                get_state=lambda dev: getattr(dev, "return_temperature", None),
                is_available=lambda dev: getattr(dev, "return_temperature", None) is not None,
            )
            entities.append(AquareaSensorEntity(coordinator, return_temp_desc))
        if hasattr(device, "compressor_status"):
            comp_desc = AquareaSensorEntityDescription(
                key="compressor_status",
                translation_key="compressor_status",
                name="Compressor Status",
                icon="mdi:engine",
                get_state=lambda dev: getattr(dev, "compressor_status", None),
                is_available=lambda dev: getattr(dev, "compressor_status", None) is not None,
            )
            entities.append(AquareaSensorEntity(coordinator, comp_desc))
        error_desc = AquareaSensorEntityDescription(
            key="error_code",
            translation_key="error_code",
            name="Error Code",
            icon="mdi:alert",
            entity_category=EntityCategory.DIAGNOSTIC,
            get_state=lambda dev: dev.current_error.error_code if dev.current_error else "none",
            is_available=lambda dev: True,
        )
        entities.append(AquareaSensorEntity(coordinator, error_desc))

        # Concrete sensors (from wpatrik14)
        entities.append(AquareaPumpDirectionSensor(coordinator))
        entities.append(AquareaPumpStatusSensor(coordinator))

        # Energy sensors
        entities.extend([
            AquareaEnergyAccumulatedConsumptionSensor(desc, coordinator)
            for desc in ACCUMULATED_ENERGY_SENSORS
            if desc.exists_fn(coordinator)
        ])
        entities.extend([
            AquareaEnergyConsumptionSensor(desc, coordinator)
            for desc in ENERGY_SENSORS
            if desc.exists_fn(coordinator)
        ])

    async_add_entities(entities)


class PanasonicSensorEntityBase(SensorEntity):
    """Base class for all sensor entities."""

    entity_description: PanasonicSensorEntityDescription  # type: ignore[override]


class PanasonicSensorEntity(PanasonicDataEntity, PanasonicSensorEntityBase):

    def __init__(
        self,
        coordinator: PanasonicDeviceCoordinator,
        description: PanasonicSensorEntityDescription,
    ):
        self.entity_description = description
        super().__init__(coordinator, description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if self.entity_description.is_available is None:
            return False
        return self.entity_description.is_available(self.coordinator.device)

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        if self.entity_description.is_available:
            self._attr_available = self.entity_description.is_available(
                self.coordinator.device
            )
        if self.entity_description.get_state:
            self._attr_native_value = self.entity_description.get_state(
                self.coordinator.device
            )


class PanasonicEnergySensorEntity(PanasonicEnergyEntity, SensorEntity):

    entity_description: PanasonicEnergySensorEntityDescription  # type: ignore[override]

    def __init__(
        self,
        coordinator: PanasonicDeviceEnergyCoordinator,
        description: PanasonicEnergySensorEntityDescription,
    ):
        self.entity_description = description
        super().__init__(coordinator, description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._attr_available

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        energy = self.coordinator.energy
        if energy is None:
            self._attr_available = False
            return
        value = self.entity_description.get_state(energy)
        self._attr_available = value is not None
        self._attr_native_value = value


class AquareaSensorEntity(AquareaDataEntity, SensorEntity):

    entity_description: AquareaSensorEntityDescription

    def __init__(
        self,
        coordinator: AquareaDeviceCoordinator,
        description: AquareaSensorEntityDescription,
    ):
        self.entity_description = description
        super().__init__(coordinator, description.key)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        value = (
            self.entity_description.is_available(self.coordinator.device)
            if self.entity_description.is_available
            else None
        )
        return value if value is not None else False

    def _async_update_attrs(self) -> None:
        """Update the attributes of the sensor."""
        if self.entity_description.is_available:
            self._attr_available = self.entity_description.is_available(
                self.coordinator.device
            )
        if self.entity_description.get_state:
            self._attr_native_value = self.entity_description.get_state(
                self.coordinator.device
            )


class AquareaPumpDirectionSensor(AquareaDataEntity, SensorEntity):
    """Sensor showing the current pump direction."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "direction")
        self._attr_icon = "mdi:compass"

    def _async_update_attrs(self) -> None:
        self._attr_native_value = self.coordinator.device.current_direction.name


class AquareaPumpStatusSensor(AquareaDataEntity, SensorEntity):
    """Sensor showing if the pump is on or off."""

    def __init__(self, coordinator: AquareaDeviceCoordinator) -> None:
        super().__init__(coordinator, "pump_status")
        self._attr_icon = "mdi:pump"

    def _async_update_attrs(self) -> None:
        self._attr_native_value = (
            "On" if self.coordinator.device.pump_duty == 1 else "Off"
        )


# --- Energy sensor state restore helpers ---

@dataclass
class AquareaSensorExtraStoredData(SensorExtraStoredData):
    period_being_processed: datetime | None = None

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self:
        sensor_data = super().from_dict(restored)
        return cls(
            native_value=sensor_data.native_value,
            native_unit_of_measurement=sensor_data.native_unit_of_measurement,
            period_being_processed=(
                dt_util.parse_datetime(restored["period_being_processed"])
                if "period_being_processed" in restored
                else None
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        data = super().as_dict()
        if self.period_being_processed is not None:
            data["period_being_processed"] = dt_util.as_local(
                self.period_being_processed
            ).isoformat()
        return data


@dataclass
class AquareaAccumulatedSensorExtraStoredData(AquareaSensorExtraStoredData):
    accumulated_period_being_processed: float | None = None

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self:
        sensor_data = super().from_dict(restored)
        return cls(
            native_value=sensor_data.native_value,
            native_unit_of_measurement=sensor_data.native_unit_of_measurement,
            period_being_processed=sensor_data.period_being_processed,
            accumulated_period_being_processed=restored.get(
                "accumulated_period_being_processed"
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        data = super().as_dict()
        data["accumulated_period_being_processed"] = (
            self.accumulated_period_being_processed
        )
        return data


class AquareaEnergyAccumulatedConsumptionSensor(
    AquareaDataEntity, SensorEntity, RestoreEntity
):
    """Accumulated (month-to-date) energy consumption sensor."""

    entity_description: AquareaEnergyConsumptionSensorDescription

    def __init__(
        self,
        description: AquareaEnergyConsumptionSensorDescription,
        coordinator: AquareaDeviceCoordinator,
    ) -> None:
        self.entity_description = description
        self._period_being_processed: datetime | None = None
        self._accumulated_period_being_processed: float | None = None
        super().__init__(coordinator, description.key)

    async def async_added_to_hass(self) -> None:
        sensor_data = await self.async_get_last_sensor_data()
        if sensor_data is not None:
            self._attr_native_value = sensor_data.native_value
            self._period_being_processed = sensor_data.period_being_processed
            self._accumulated_period_being_processed = (
                sensor_data.accumulated_period_being_processed
            )
        if self._attr_native_value is None:
            self._attr_native_value = 0
        if self._accumulated_period_being_processed is None:
            self._accumulated_period_being_processed = 0
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> AquareaAccumulatedSensorExtraStoredData:
        return AquareaAccumulatedSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._period_being_processed,
            self._accumulated_period_being_processed,
        )

    async def async_get_last_sensor_data(
        self,
    ) -> AquareaAccumulatedSensorExtraStoredData | None:
        if (restored := await self.async_get_last_extra_data()) is None:
            return None
        return AquareaAccumulatedSensorExtraStoredData.from_dict(restored.as_dict())

    def _async_update_attrs(self) -> None:
        month_consumption = self.coordinator.month_consumption
        if not month_consumption:
            return

        now = dt_util.now()
        month_heat = month_cool = month_tank = month_total = 0.0
        for c in month_consumption:
            try:
                dt_str = c.data_time
                if not dt_str:
                    continue
                item_date = None
                for fmt in ("%Y%m%d", "%Y-%m-%d"):
                    try:
                        item_date = datetime.strptime(dt_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if item_date is None:
                    continue
                if item_date <= now.date():
                    month_heat += float(c.heat_consumption or 0.0)
                    month_cool += float(c.cool_consumption or 0.0)
                    month_tank += float(c.tank_consumption or 0.0)
                    try:
                        month_total += float(c.total_consumption or 0.0)
                    except (ValueError, TypeError):
                        month_total += month_heat + month_cool + month_tank
            except (ValueError, TypeError):
                _LOGGER.debug("Failed to parse month consumption item")

        ctype = self.entity_description.consumption_type
        reported_val = None
        if ctype == aioaquarea.ConsumptionType.HEAT:
            reported_val = month_heat
        elif ctype == aioaquarea.ConsumptionType.COOL:
            reported_val = month_cool
        elif ctype == aioaquarea.ConsumptionType.WATER_TANK:
            reported_val = month_tank
        elif ctype == aioaquarea.ConsumptionType.TOTAL:
            reported_val = month_total
        if reported_val is not None:
            month_start = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            self._period_being_processed = month_start
            self._attr_native_value = reported_val


class AquareaEnergyConsumptionSensor(
    AquareaDataEntity, SensorEntity, RestoreEntity
):
    """Hourly energy consumption sensor."""

    entity_description: AquareaEnergyConsumptionSensorDescription

    def __init__(
        self,
        description: AquareaEnergyConsumptionSensorDescription,
        coordinator: AquareaDeviceCoordinator,
    ) -> None:
        self.entity_description = description
        self._period_being_processed: datetime | None = None
        super().__init__(coordinator, description.key)

    async def async_added_to_hass(self) -> None:
        sensor_data = await self.async_get_last_sensor_data()
        if sensor_data is not None:
            self._attr_native_value = sensor_data.native_value
            self._period_being_processed = sensor_data.period_being_processed
        if self._attr_native_value is None:
            self._attr_native_value = 0
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> AquareaSensorExtraStoredData:
        return AquareaSensorExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._period_being_processed,
        )

    async def async_get_last_sensor_data(
        self,
    ) -> AquareaSensorExtraStoredData | None:
        if (restored := await self.async_get_last_extra_data()) is None:
            return None
        return AquareaSensorExtraStoredData.from_dict(restored.as_dict())

    def _async_update_attrs(self) -> None:
        day_consumption = self.coordinator.day_consumption
        if not day_consumption:
            return

        now = dt_util.now().replace(minute=0, second=0, microsecond=0)
        previous_hour_dt = now - timedelta(hours=1)
        target_hour = previous_hour_dt.hour
        target_date = previous_hour_dt.date()
        current_entry = None

        for c in day_consumption:
            dt_str = c.data_time
            if not dt_str:
                continue
            try:
                item_dt = None
                for fmt in ("%Y%m%d %H", "%Y-%m-%d %H"):
                    try:
                        item_dt = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue
                if (
                    item_dt
                    and item_dt.date() == target_date
                    and item_dt.hour == target_hour
                ):
                    current_entry = c
                    break
            except (ValueError, TypeError):
                pass

        if current_entry is None:
            for c in reversed(day_consumption):
                dt_str = c.data_time
                if not dt_str:
                    continue
                try:
                    for fmt in ("%Y%m%d %H", "%Y-%m-%d %H"):
                        try:
                            item_dt = datetime.strptime(dt_str, fmt)
                            current_entry = c
                            break
                        except ValueError:
                            continue
                    if current_entry:
                        break
                except (ValueError, TypeError):
                    pass

        if current_entry:
            ctype = self.entity_description.consumption_type
            reported_val = None
            if ctype == aioaquarea.ConsumptionType.HEAT:
                reported_val = float(current_entry.heat_consumption or 0.0)
            elif ctype == aioaquarea.ConsumptionType.COOL:
                reported_val = float(current_entry.cool_consumption or 0.0)
            elif ctype == aioaquarea.ConsumptionType.WATER_TANK:
                reported_val = float(current_entry.tank_consumption or 0.0)
            elif ctype == aioaquarea.ConsumptionType.TOTAL:
                try:
                    reported_val = float(current_entry.total_consumption or 0.0)
                except (ValueError, TypeError):
                    reported_val = float(
                        (current_entry.heat_consumption or 0.0)
                        + (current_entry.cool_consumption or 0.0)
                        + (current_entry.tank_consumption or 0.0)
                    )
            self._period_being_processed = now
            self._attr_native_value = reported_val
