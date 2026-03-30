# Aquarea Integration — Findings (2026-03-28)

Findings from live exploration against device **"Pump" (B116146854)** using `aioaquarea==1.0.3`.

---

## Device facts

| Field | Value |
|-------|-------|
| Device ID | B116146854 |
| Name | Pump |
| Mode | Heat-only (no cool mode on zones) |
| Has tank | Yes |
| Outdoor temp (at time of test) | 4°C |
| Zones | 2 |
| Special status support | Yes (ECO / COMFORT) |

### Zone 1
- Operation status: ON
- Current temp: 27°C → target 26°C
- Heat range: 20–60°C
- ECO modifier: −5°C / COMFORT modifier: +5°C

### Zone 2
- Operation status: OFF
- All temps: None (inactive)

### Tank
- Operation status: ON
- Current temp: 53°C
- Target temp: 52°C
- Heat range: 40–65°C

---

## Bug 1 — Library token sync (`aioaquarea`)

**Severity: Critical** — causes re-auth on every coordinator poll.

**Root cause:** `get_devices()` returns a rotated access token in the JSON response body. `api_client.request()` updates `api_client._access_token` from it, but NOT `settings.access_token`. All subsequent requests build headers from `settings.access_token` (via `PanasonicRequestHeader.get(settings, ...)`), which is still the original OAuth token. The server rejects it with `TOKEN_EXPIRED`.

**Affected files:** `coordinator.py` (`AquareaDeviceCoordinator._fetch_device_data`)

**Workaround (applied in `scripts/explore_aquarea.py`):**
```python
# After get_devices(), sync the rotated token back to settings
if client._api_client.access_token and client._api_client.access_token != client._settings.access_token:
    client._settings.access_token = client._api_client.access_token
```

**Fix in coordinator:** Add the same sync after the first `get_device()` call, or wrap all Aquarea API calls in a helper that keeps `settings.access_token` in sync with `api_client.access_token`.

---

## Bug 2 — Tank temperature sensor never registered

**Severity: High** — live tank temp (53°C) is never shown in HA.

**Location:** `sensor.py:261`

**Root cause:** The sensor guard uses `hasattr(device, 'tank_temperature')` — this attribute does not exist on `Device`. The correct path is `device.tank.temperature` (via the `Tank` object).

**Fix:**
```python
# Replace:
if hasattr(device, "tank_temperature"):
    ...get_state=lambda dev: getattr(dev, "tank_temperature", None)

# With:
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
```

---

## Bug 3 — Zone temperature sensors never registered

**Severity: High** — zone temps (27°C / 0°C) never shown in HA.

**Location:** `sensor.py:275`

**Root cause:** `getattr(device, 'zones', [])` returns the dict `device.zones` but then iterates it as a list — iterating a `dict` yields keys (integers), not `DeviceZone` objects. The `hasattr(zone, 'temperature')` check on an `int` is always False.

**Fix:**
```python
# Replace:
for zone in getattr(device, "zones", []):
    if hasattr(zone, "temperature"):

# With:
for zone in device.zones.values():
    zone_temp_desc = AquareaSensorEntityDescription(
        key=f"zone_{zone.zone_id}_temperature",
        translation_key=f"zone_temperature",
        name=f"{zone.name} Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        get_state=lambda dev, zid=zone.zone_id: dev.zones[zid].temperature if zid in dev.zones else None,
        is_available=lambda dev, zid=zone.zone_id: zid in dev.zones,
    )
    entities.append(AquareaSensorEntity(coordinator, zone_temp_desc))
```

---

## Bug 4 — Switches never registered (force_dhw, force_heater, holiday_timer)

**Severity: High** — all Aquarea switches are dead code.

**Location:** `switch.py:130–209`

**Root cause:** Guards use `hasattr(device, 'has_force_dhw')`, `hasattr(device, 'has_force_heater')` etc. None of these `has_*` attributes exist on `Device`. The actual attributes are `device.force_dhw`, `device.force_heater`, `device.holiday_timer` (always present, `IntEnum` values).

The `on_func`/`off_func` lambdas are also wrong — they call `builder.set_*()` (Panasonic CC builder pattern) instead of `await device.set_*()` (Aquarea direct async calls). The existing `AquareaSwitchEntity` correctly calls `await description.on_func(device)` so the lambda signatures just need fixing.

**Fix (Holiday Timer):**
```python
# Replace:
if hasattr(device, "holiday_timer") and hasattr(device, "set_holiday_timer"):
    hol_desc = AquareaSwitchEntityDescription(
        ...
        on_func=lambda dev: dev.set_holiday_timer(1 if type(...) == "int" else aioaquarea.HolidayTimer.ON),
        off_func=...,
        get_state=lambda dev: getattr(dev.holiday_timer, "name", ...) == "ON" or dev.holiday_timer == 1,
    )

# With:
if hasattr(device, "holiday_timer"):
    hol_desc = AquareaSwitchEntityDescription(
        key="holiday_timer",
        translation_key="holiday_timer",
        name="Holiday Timer",
        icon="mdi:calendar-clock",
        on_func=lambda dev: dev.set_holiday_timer(aioaquarea.HolidayTimer.ON),
        off_func=lambda dev: dev.set_holiday_timer(aioaquarea.HolidayTimer.OFF),
        get_state=lambda dev: dev.holiday_timer == aioaquarea.HolidayTimer.ON,
        is_available=lambda dev: True,
    )
    devices.append(AquareaSwitchEntity(coordinator, hol_desc))
```

**Same pattern for:**
- `force_dhw` → guard: `hasattr(device, 'force_dhw')`, calls `device.set_force_dhw(ForceDHW.ON/OFF)`
- `force_heater` → guard: `hasattr(device, 'force_heater')`, calls `device.set_force_heater(ForceHeater.ON/OFF)`

The `has_nanoe`, `has_eco_mode`, `has_powerful_mode`, `has_defrost` guards also never match — these features do not exist on `aioaquarea.Device`. Remove those blocks entirely.

---

## Bug 5 — Error sensor never registered

**Severity: Medium** — fault codes never shown in HA (binary sensor only shows is_on_error).

**Location:** `sensor.py:344`

**Root cause:** `hasattr(device, 'error_code')` is always False. The error data lives at `device.current_error.error_code` and `device.current_error.error_message`, gated by `device.is_on_error`.

**Fix:**
```python
# Replace the hasattr(device, 'error_code') / hasattr(device, 'alarm_code') blocks with:
error_desc = AquareaSensorEntityDescription(
    key="error_code",
    translation_key="error_code",
    name="Error Code",
    icon="mdi:alert",
    entity_category=EntityCategory.DIAGNOSTIC,
    get_state=lambda dev: dev.current_error.error_code if dev.current_error else None,
    is_available=lambda dev: dev.is_on_error,
)
entities.append(AquareaSensorEntity(coordinator, error_desc))
```

---

## Additional observations

### Zone names
`DeviceManager.get_devices()` mocks zone names as `"Zone {zone_id}"` — the real zone name is not returned by the groups API. Zone 1 and Zone 2 in HA will have generic names unless the Aquarea app also uses them.

### DeviceAction.HEATING_WATER
When the heat pump is actively heating DHW (tank), `device.current_action` returns `DeviceAction.HEATING_WATER`. The zone climate entity's `convert_aquarea_action_to_hvac_action()` in `climate.py:156` only handles `COOLING` and `HEATING`, falling through to `IDLE` for `HEATING_WATER`. This is arguably correct for zone climate entities (space heating is idle while tank runs), but the `water_heater` entity could use this to show an active heating action.

### special_status hardcoded to None
`DeviceManager.get_device_status()` always sets `special_status=None` (line 255 in `device_manager.py`). The `SpecialStatus` select entity in `select.py` will never reflect the real ECO/COMFORT status.

---

## Before fixing: check for library updates

Several of the bugs above may already be fixed in newer versions of `aioaquarea` or `aio-panasonic-comfort-cloud`. Before writing workarounds in the integration code, check the upstream changelogs and test with the latest releases.

| Bug | Likely fixed upstream? | What to check |
|-----|----------------------|---------------|
| Token sync (`settings.access_token` not updated) | Possibly — this is a clear library bug | `aioaquarea` changelog / git log on `api_client.py` |
| `special_status` hardcoded to `None` | Possibly — looks like an incomplete implementation | `aioaquarea` changelog / `device_manager.py` |
| Zone names mocked as `"Zone {id}"` | Possibly | `aioaquarea` changelog / `device_manager.py` |
| `tank_temperature` / zone iteration bugs | Unlikely — these are integration bugs, not library bugs | N/A |
| Switch guard conditions (`has_*` flags) | Unlikely — integration bug | N/A |

**How to test a library bump:**

```bash
# Try the latest aioaquarea
uv add aioaquarea@latest
uv run scripts/explore_aquarea.py

# Or pin a specific version to compare
uv add aioaquarea==1.1.0
uv run scripts/explore_aquarea.py
```

If a library update fixes a bug, update `manifest.json` requirements[] and `requirements.txt` to match, and drop any workarounds from integration code.

---

## HA API compatibility validation

> **Validated 2026-03-30** against `homeassistant==2026.3.4`, `pytest-homeassistant-custom-component==0.13.320`, `mypy==1.19.1`, `pytest-asyncio==1.3.0`.

The integration is currently tested by running it inside a real HA instance. There is no automated way to catch drift when HA releases breaking changes to platform interfaces (`ClimateEntity`, `WaterHeaterEntity`, `CoordinatorEntity`, etc.). The following tools exist to close that gap — all were verified to install and run.

### 1. Static type checking with `mypy` ✅ verified

HA ships full type annotations. `homeassistant` installs cleanly as a dev dependency alongside our existing runtime deps (confirmed — 290 packages, resolves without hard conflicts). `mypy` runs against the integration today.

**Tested:** `uv run mypy custom_components/panasonic_cc/ --ignore-missing-imports`

**Result: 58 errors across 10 files.** Breakdown:

| File | Errors |
|------|--------|
| `select.py` | 14 |
| `climate.py` | 11 |
| `switch.py` | 7 |
| `number.py` | 7 |
| `button.py` | 6 |
| `water_heater.py` | 4 |
| `binary_sensor.py` | 3 |
| `__init__.py` | 3 |
| `coordinator.py` | 2 |
| `sensor.py` | 1 |

Notable errors already visible without HA types (i.e. pure Python issues):
- `binary_sensor.py`: `callable` used as a type annotation instead of `typing.Callable`
- `switch.py`: `AquareaDevice` and `Any` used in type hints without being imported; `AquareaSwitchEntity` appended to a `list[PanasonicSwitchEntity]`
- `number.py`: lambda return types incompatible with `get_value: Callable[[Any], int]`

**Dependency conflict note:** Installing `homeassistant` downgrades `yarl` (1.23→1.22) and `attrs` (26.1→25.4) due to HA's pinned requirements. Verified these downgrades do not break `aioaquarea` or `aiohttp` imports.

**To add to `pyproject.toml` when ready:**
```toml
[dependency-groups]
dev = [
    "ipython",
    "python-dotenv",
    "homeassistant>=2026.3.4",   # tested against this — bump as HA releases
    "mypy>=1.19.1",
    "pytest-homeassistant-custom-component>=0.13.320",
    "pytest-asyncio>=1.3.0",
]
```

**Also: `manifest.json` minimum HA version is `2024.12.1` — 15+ months old as of 2026-03-30.**
This should be reviewed and bumped. Declaring an old minimum gives a false guarantee of compatibility and hides deprecation warnings that HA would only surface on recent versions. Suggested: bump to `2025.12.0` or later, validate nothing breaks, then keep it rolling forward each year.

### 2. `pytest-homeassistant-custom-component` ✅ verified (installs, not yet run)

Package exists at `0.13.320` and installs as part of the same `homeassistant` dep group above — it's included transitively. Provides a real (lightweight) HA core, config entry helpers, and entity registry fixtures.

Not yet run against this integration — no test files exist yet. A minimal smoke test that would have caught all 5 Aquarea entity bugs: assert that the expected entities are registered after `async_setup_entry` with a mocked `aioaquarea.Device`.

### 3. `hassfest` — HA's own manifest linter ⚠️ not standalone

`hassfest` is HA's validation script for `manifest.json`, `strings.json`, `translations/`, `services.yaml`, and `icons.json`. It is **not available as a standalone PyPI package** — it ships inside the HA core repo at `script/hassfest` and requires a checked-out HA core to run.

Options:
- Run via the [HA dev container](https://developers.home-assistant.io/docs/development_environment) (Docker)
- Run in CI by checking out HA core alongside this repo

Not yet set up locally. Worth doing once the entity bugs are fixed, as `quality_scale: silver` has manifest requirements that may have drifted.

### 4. Testing against HA beta ⚠️ not yet set up

HA publishes beta releases ~2 weeks before stable. HA deprecation warnings appear as `DeprecationWarning` in Python and can be promoted to errors in pytest:

```ini
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = ["error::DeprecationWarning"]
```

Not yet set up. Practical approach when tests exist: maintain two lockfiles (`uv.lock` for current stable, a separate resolve for the current beta) and run both in CI.

### 5. Known drift risks (read from HA changelog, not yet validated by tooling)

| Area | Risk | Status |
|------|------|--------|
| Horizontal swing | Integration uses a custom service; HA 2024.x added native `ClimateEntityFeature.SWING_HORIZONTAL_MODE` — the native path is unused | Unvalidated |
| `ConfigEntry` generics | HA moving toward typed `ConfigEntry[T]` — untyped entries will warn in future releases | Unvalidated |
| `WaterHeaterEntity` | `supported_features` should use `WaterHeaterEntityFeature` flags | mypy will surface this |

---

## Dev environment

```
uv sync --dev          # install .venv with all deps
uv run scripts/explore_aquarea.py   # live device inspection (needs .env)
```

Dep management: `pyproject.toml` → `uv.lock` (lockfile). When bumping a runtime dep, also update `manifest.json` requirements[].

**⚠️ Panasonic API rate limiting:** Panasonic is very aggressive at blocking clients and IPs that hit their auth endpoint too frequently. Run `explore_aquarea.py` sparingly — one run per session is enough. Do not loop it, do not run it in CI against the real API, and never test auth flows in a tight retry loop. Any future automated tests must mock the `aioaquarea.Client` entirely and never call the real API.
