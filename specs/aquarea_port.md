# Aquarea Entity Port Specification

Port wpatrik14's Aquarea entity implementations into this integration.
Source: `/tmp/home-assistant-aquarea/custom_components/aquarea/`

**Motivation:** Our Aquarea entities are a rough first attempt. wpatrik14's are complete, correct,
and actively maintained. We keep our Panasonic CC (split AC) side untouched. We keep our
`AquareaDeviceCoordinator` and config flow as the backbone; we replace or rewrite the Aquarea
entity code in each platform file.

---

## Architecture differences to account for

| Concern | wpatrik14 | Ours (keep) |
|---------|-----------|-------------|
| Coordinator base | `DataUpdateCoordinator`, `_async_update_data` returns device | `DataUpdateCoordinator`, same — but `device` stored in `self._device`, not `self.data` |
| `coordinator.device` | `self.data` (returned from `_async_update_data`) | `self._device` property — keep as-is |
| Force re-fetch | `async_request_refresh(force_fetch=True)` sets `_device = None` | Need to add same |
| Consumption data | Fetched in coordinator, tiered (daily 15m, monthly configurable) | Not fetched — needs adding |
| Base entity class | `AquareaBaseEntity` in `__init__.py` | `AquareaDataEntity` in `base.py` — keep, adapt callers |
| `_handle_coordinator_update` | `@callback`, writes state, called explicitly | Same pattern — keep |
| `device_info` | from `coordinator.device_info` (lib `DeviceInfo`) | Same — keep |

When porting entity code, replace `AquareaBaseEntity` → `AquareaDataEntity`, replace
`coordinator.data` → `coordinator.device`, and replace `coordinator.async_request_refresh(force_fetch=True)`
with whatever we add to our coordinator.

---

## 1. coordinator.py — Enhance AquareaDeviceCoordinator

**File:** `custom_components/panasonic_cc/coordinator.py`

### Add: `async_request_refresh(force_fetch=True)`
When `force_fetch=True`, set `self._device = None` before refreshing so the next
`_fetch_device_data` call does a full `get_device()` rather than just `refresh_data()`.

```python
async def async_request_refresh(self, force_fetch: bool = False) -> None:
    if force_fetch:
        self._device = None
    await super().async_request_refresh()
```

### Add: tiered consumption fetching
Add to `_fetch_device_data` (after device refresh succeeds):
- `_day_consumption` — fetched every 15 min via `client.get_device_consumption(long_id, DateType.DAY, date_str)`
- `_month_consumption` — fetched every N min (configurable, default 60) via `DateType.MONTH`
- Track `_last_daily_fetch_time` and `_last_monthly_fetch_time` as `datetime | None`
- Expose `day_consumption` and `month_consumption` as properties

Rate limit: only fetch if elapsed time since last fetch exceeds the interval. Use `asyncio.gather`
for parallel daily + monthly fetch when both are due.

Source reference: `coordinator.py:101–183` in wpatrik14.

---

## 2. climate.py — Replace AquareaClimateEntity

**File:** `custom_components/panasonic_cc/climate.py`

The existing `AquareaClimateEntity` should be replaced with the `HeatPumpClimate` pattern.
Keep all Panasonic CC climate code untouched.

### Add module-level helpers (new, from wpatrik14 `climate.py:38–115`)
```python
SPECIAL_STATUS_LOOKUP: dict[str, SpecialStatus | None] = {
    PRESET_ECO: SpecialStatus.ECO,
    PRESET_COMFORT: SpecialStatus.COMFORT,
    PRESET_NONE: None,
}
SPECIAL_STATUS_REVERSE_LOOKUP = {v: k for k, v in SPECIAL_STATUS_LOOKUP.items()}

CLIMATE_DELAY_SHORT = 5.0   # after set_temperature
CLIMATE_DELAY_LONG  = 10.0  # after set_hvac_mode, set_preset_mode, turn_on/off

def get_hvac_mode_from_ext_op_mode(mode, zone_status, device_status) -> HVACMode: ...
def get_hvac_action_from_device_direction(direction, hvac_mode) -> HVACAction: ...
def get_update_operation_mode_from_hvac_mode(mode) -> UpdateOperationMode: ...
```

### Replace AquareaClimateEntity (`climate.py`, Aquarea section)

New class `AquareaClimateEntity(AquareaDataEntity, ClimateEntity)`:

**`__init__`:**
- `supported_features = TARGET_TEMPERATURE | TURN_ON | TURN_OFF`
- If `device.support_special_status`: add `PRESET_MODE`, set `preset_modes`, set initial `preset_mode`
- `hvac_modes = [HEAT, COOL, AUTO, OFF]`
- Store `_zone_id`

**`_async_update_attrs` (replaces `_handle_coordinator_update`):**
- `hvac_mode` via `get_hvac_mode_from_ext_op_mode(device.mode, zone.operation_status, device.operation_status)`
- `hvac_action` via `get_hvac_action_from_device_direction(device.current_direction, hvac_mode)`
- `current_temperature = zone.temperature`
- `target_temperature`: `zone.cool_target_temperature` if mode is COOL/AUTO_COOL, else `zone.heat_target_temperature`
- `min_temp` / `max_temp`: cool or heat range if `zone.supports_set_temperature and mode != OFF`, else freeze to current temp
- `preset_mode` if `support_special_status`

**`_schedule_refresh(delay)`:** `asyncio.sleep(delay)` then `coordinator.async_request_refresh(force_fetch=True)`

**`async_set_hvac_mode`:** optimistic update → `device.set_mode(...)` → rollback on exception → schedule refresh (LONG)

**`async_set_temperature`:** optimistic update → `device.set_temperature(int(temp), zone_id)` if `zone.supports_set_temperature` → rollback on exception → schedule refresh (SHORT)

**`async_set_preset_mode`:** optimistic update → `device.set_special_status(SPECIAL_STATUS_LOOKUP[preset])` → rollback → schedule refresh (LONG)

**`async_turn_on`:** optimistic HEAT → `device.turn_on()` → rollback → schedule refresh (LONG)

**`async_turn_off`:** optimistic OFF → `device.turn_off()` → rollback → schedule refresh (LONG)

Source reference: `climate.py:118–342` in wpatrik14.

---

## 3. switch.py — Replace Aquarea switch entities

**File:** `custom_components/panasonic_cc/switch.py`

Keep all Panasonic CC switch code. Replace the Aquarea section with dedicated entity classes
(not the description-based approach — individual classes like wpatrik14).

Remove `AquareaSwitchEntityDescription` dataclass and `AquareaSwitchEntity` generic class.
Replace with three concrete classes:

### `AquareaForceDHWSwitch(AquareaDataEntity, SwitchEntity)`
- Only registered if `device.has_tank`
- `_optimistic_is_on: bool | None = None`
- `is_on`: returns optimistic if set, else `device.force_dhw is ForceDHW.ON`
- `async_turn_on`: optimistic True → `device.set_force_dhw(ForceDHW.ON)` → schedule refresh
- `async_turn_off`: optimistic False → `device.set_force_dhw(ForceDHW.OFF)` → schedule refresh
- `_schedule_refresh`: sleep 10s → clear optimistic → `coordinator.async_request_refresh(force_fetch=True)`
- Icon: `mdi:water-boiler` / `mdi:water-boiler-off`

### `AquareaForceHeaterSwitch(AquareaDataEntity, SwitchEntity)`
- Always registered (no guard needed)
- Same pattern with `device.force_heater` / `ForceHeater.ON/OFF`
- Icon: `mdi:hvac` / `mdi:hvac-off`

### `AquareaHolidayTimerSwitch(AquareaDataEntity, SwitchEntity)`
- Always registered
- Same pattern with `device.holiday_timer` / `HolidayTimer.ON/OFF`
- Icon: `mdi:timer-check` / `mdi:timer-off`

**`_async_update_attrs`** on each: set `_attr_available = True`, update `_attr_is_on` from device
(not the optimistic value — let the property handle that).

Source reference: `switch.py:43–189` in wpatrik14.

---

## 4. select.py — Replace Aquarea select entities

**File:** `custom_components/panasonic_cc/select.py`

Keep all Panasonic CC select code. Replace the Aquarea section.

### Remove
- Existing `AquareaSelectEntityDescription`, `AquareaSelectEntity`, and all Aquarea guards in
  `async_setup_entry` that use `has_*` flags or `support_*` checks.

### Add: `AquareaQuietModeSelect(AquareaDataEntity, SelectEntity)`
```python
QUIET_MODE_LOOKUP = {
    "level1": QuietMode.LEVEL1, "level2": QuietMode.LEVEL2,
    "level3": QuietMode.LEVEL3, "off": QuietMode.OFF,
}
```
- `_optimistic_option: str | None = None`
- `current_option`: return optimistic if set, else `QUIET_MODE_REVERSE_LOOKUP[device.quiet_mode]`
- `async_select_option`: skip if same, optimistic → `device.set_quiet_mode(mode)` → schedule refresh
- `_schedule_refresh`: sleep 10s → clear optimistic → `coordinator.async_request_refresh()`

### Add: `AquareaPowerfulTimeSelect(AquareaDataEntity, SelectEntity)`
```python
POWERFUL_TIME_LOOKUP = {
    "off": PowerfulTime.OFF, "on-30m": PowerfulTime.ON_30MIN,
    "on-60m": PowerfulTime.ON_60MIN, "on-90m": PowerfulTime.ON_90MIN,
}
```
- Same optimistic pattern
- Dynamic icon: `mdi:fire` / `mdi:fire-off`
- `async_select_option`: `device.set_powerful_time(powerful_time)` → schedule refresh

Source reference: `select.py:56–150` in wpatrik14.

---

## 5. water_heater.py — Rewrite Aquarea water heater entity

**File:** `custom_components/panasonic_cc/water_heater.py`

### Fix existing entity

**`__init__`:**
- `supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.OPERATION_MODE`
- `operation_list = [HEATING, STATE_OFF]` (define `HEATING = "heating"`, `IDLE = "idle"` as constants)

**`_async_update_attrs`:**
- `min_temp = device.tank.heat_min`, `max_temp = device.tank.heat_max`
- `target_temperature = device.tank.target_temperature`
- `current_temperature = device.tank.temperature`
- Operation state:
  - OFF if `tank.operation_status == OperationStatus.OFF`
  - Active heating detection: `current_direction == DeviceDirection.WATER` → `HEATING`
  - Fallback: check `DeviceAction.HEATING_WATER` → `HEATING`, else `IDLE`
  - Use `STATE_HEAT_PUMP` (from HA) as `_attr_state` when on, `STATE_OFF` when off

**`async_set_temperature`:** optimistic → `device.tank.set_target_temperature(int(temp))` → schedule refresh

**`async_set_operation_mode`:**
- `HEATING` → `device.tank.turn_on()`
- `STATE_OFF` → `device.tank.turn_off()`
- Schedule refresh after

**`_schedule_refresh`:** sleep 10s → `coordinator.async_request_refresh(force_fetch=True)`

Source reference: `water_heater.py:52–179` in wpatrik14.

---

## 6. sensor.py — Add Aquarea sensors

**File:** `custom_components/panasonic_cc/sensor.py`

Keep all existing Aquarea sensors (outside temp, tank temp, zone temps, error code, pump_duty,
current_direction, device_mode_status). Add:

### `AquareaPumpDirectionSensor(AquareaDataEntity, SensorEntity)`
- `get_state`: `device.current_direction.name`
- Icon: `mdi:compass`

### `AquareaPumpStatusSensor(AquareaDataEntity, SensorEntity)`
- `get_state`: `"On"` if `device.pump_duty == 1` else `"Off"`
- Icon: `mdi:pump`

### Energy sensors (requires coordinator consumption data — do after coordinator update)

Four accumulated (`SensorStateClass.TOTAL_INCREASING`) + four periodic (`SensorStateClass.TOTAL`,
disabled by default) sensors, one each for heat / cool / tank / total consumption.

- Use `RestoreEntity` mixin to survive HA restarts
- `exists_fn` guards: cooling sensors only if `any(z.cool_mode for z in device.zones.values())`,
  tank sensor only if `device.has_tank`
- Read from `coordinator.day_consumption` (hourly) and `coordinator.month_consumption` (monthly)

Source reference: `sensor.py:30–406` in wpatrik14.

---

## 7. binary_sensor.py — Add Aquarea defrost sensor

**File:** `custom_components/panasonic_cc/binary_sensor.py`

### Add: `AquareaDefrostBinarySensor(AquareaDataEntity, BinarySensorEntity)`
- `device_class = BinarySensorDeviceClass.RUNNING`
- `is_on`: `device.device_mode_status is DeviceModeStatus.DEFROST`
- Icon: `mdi:snowflake-melt` / `mdi:snowflake-off`

Source reference: `binary_sensor.py:59–78` in wpatrik14.

---

## 8. button.py — Fix Aquarea defrost button

**File:** `custom_components/panasonic_cc/button.py`

The existing defrost button probably exists but may not guard against already-defrosting state.

### Fix `async_press`:
Add guard: only call `device.request_defrost()` if
`device.device_mode_status is not DeviceModeStatus.DEFROST`.

Source reference: `button.py:47–54` in wpatrik14.

---

## Implementation order

1. **coordinator.py** — Add `async_request_refresh(force_fetch)` first (other entities depend on it). Consumption fetching can come after energy sensors.
2. **switch.py** — Replace Aquarea switches (concrete classes). Simplest port.
3. **select.py** — Replace Aquarea selects. Simple port.
4. **water_heater.py** — Fix entity. Medium complexity.
5. **climate.py** — Replace AquareaClimateEntity. Most complex, do after coordinator is ready.
6. **binary_sensor.py** — Add defrost sensor. Trivial.
7. **button.py** — Fix defrost guard. Trivial.
8. **sensor.py** — Add pump sensors (easy). Energy sensors depend on coordinator consumption (last).
9. **coordinator.py** (round 2) — Add consumption fetching.
10. **sensor.py** (round 2) — Add energy sensors.

---

## What NOT to port

- wpatrik14's `coordinator.py` in full — ours has different structure; only port specific patterns
- wpatrik14's `config_flow.py` — ours handles both CC + Aquarea
- wpatrik14's `__init__.py` setup — ours is the multi-integration entry point
- wpatrik14's `const.py` — merge any missing constants selectively

## Tests to add/update after each step

Each ported platform needs a test that:
1. Asserts the expected entities are registered (same pattern as existing tests)
2. For write entities (switches, selects, climate): assert the correct aioaquarea method is called
   with the correct argument when turned on/off or set
