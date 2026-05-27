"""
Aquarea auth + device inspection script.

Usage:
    cp .env.example .env  # fill in credentials
    uv run scripts/explore_aquarea.py

Or inline:
    AQUAREA_USER=foo@bar.com AQUAREA_PASS=secret uv run scripts/explore_aquarea.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import aiohttp
import aioaquarea
from aioaquarea import Client, AquareaEnvironment
from aioaquarea.data import (
    Device,
    DeviceAction,
    DeviceDirection,
    DeviceModeStatus,
    ExtendedOperationMode,
    ForceDHW,
    ForceHeater,
    HolidayTimer,
    OperationStatus,
    PowerfulTime,
    QuietMode,
    SpecialStatus,
)
from aioaquarea.errors import AuthenticationError, RequestFailedError, ApiError, ClientError


DUMP_DIR = Path(__file__).parent.parent / "api_dumps"


def hr(title=""):
    print(f"\n{'─'*60}")
    if title:
        print(f"  {title}")
        print(f"{'─'*60}")


def save_dump(name: str, data: dict) -> Path:
    DUMP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"{ts}_{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  [dump] {path}")
    return path


def sync_api_token(client: Client) -> None:
    """Keep aioaquarea's settings and low-level API client token state aligned."""
    client._api_client.access_token = client._settings.access_token
    if client._settings.expires_at:
        client._api_client.token_expiration = datetime.fromtimestamp(
            client._settings.expires_at, tz=timezone.utc
        )


def is_auth_or_token_error(err: BaseException) -> bool:
    """Return True for direct or wrapped auth/token failures."""
    current: BaseException | None = err
    while current is not None:
        if isinstance(current, AuthenticationError):
            return True
        message = str(current).lower()
        if "token" in message or "auth" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


async def retry_once_after_login(client: Client, action, description: str):
    """Run an API action, re-login once if a token/auth failure is raised."""
    for attempt in (1, 2):
        try:
            return await action()
        except (AuthenticationError, RequestFailedError, ApiError, ClientError) as err:
            if attempt == 2 or not is_auth_or_token_error(err):
                raise
            print(f"  [auth retry] {description} failed with {err}; logging in again")
            await client.login()
            sync_api_token(client)
    raise RuntimeError(f"{description} failed after auth retry")


async def main():
    user = os.getenv("AQUAREA_USER")
    password = os.getenv("AQUAREA_PASS")

    if not user or not password:
        print("Set AQUAREA_USER and AQUAREA_PASS in your .env file (copy .env.example)")
        print("Note: Panasonic's demo env is broken in aioaquarea 1.0.3 — real credentials required.")
        sys.exit(1)

    env = AquareaEnvironment.PRODUCTION

    hr("Connecting")
    print(f"  Environment : {env.name}")
    print(f"  User        : {user}")

    async with aiohttp.ClientSession() as session:
        client = Client(session, username=user, password=password, environment=env)

        # --- Auth ---
        try:
            await client.login()
            sync_api_token(client)
            print("  Auth        : OK")
        except Exception as e:
            print(f"  Auth FAILED : {e}")
            print("\nTip: If you use 2FA, SMS must be selected (not email).")
            print("     Try signing out of the Panasonic app and back in to reset 2FA method.")
            sys.exit(1)

        # Prime _api_client.access_token so token rotations in API responses are
        # captured. Without this it stays None and the rotation guard in
        # api_client.request() never fires, causing TOKEN_EXPIRED on follow-up calls.
        sync_api_token(client)

        # Wrap _api_client.request to capture raw JSON responses and keep tokens in sync.
        _raw_request = client._api_client.request

        async def _capturing_request(method, *args, **kwargs):
            resp = await _raw_request(method, *args, **kwargs)
            # Sync any token rotation that api_client captured back to settings.
            if client._api_client.access_token and client._api_client.access_token != client._settings.access_token:
                print(f"  [token rotated, syncing]")
                client._settings.access_token = client._api_client.access_token
            # Wrap the response so json() also saves a dump.
            _orig_json = resp.json

            async def _json_and_dump(**jkw):
                data = await _orig_json(**jkw)
                url = str(resp.url)
                label = url.split("/")[-1].split("?")[0] or "response"
                save_dump(label, data)
                return data

            resp.json = _json_and_dump
            return resp

        client._api_client.request = _capturing_request

        # --- Device list ---
        device_list = await client.get_devices()
        hr(f"Devices found: {len(device_list)}")
        for di in device_list:
            print(f"  id={di.device_id}  name={di.name}  model={di.model}  has_tank={di.has_tank}")

        if not device_list:
            print("No devices. Exiting.")
            return

        # Use first device
        device_info = device_list[0]
        hr(f"Loading device: {device_info.name}")

        device: Device = await retry_once_after_login(
            client,
            lambda: client.get_device(
                device_info=device_info,
                timezone=timezone(timedelta(hours=1)),
            ),
            "device load",
        )
        print("  Loaded OK")

        # ── Identity ──────────────────────────────────────────────
        hr("Identity")
        print(f"  device_id        : {device.device_id}")
        print(f"  long_id          : {device.long_id}")
        print(f"  device_name      : {device.device_name}")
        print(f"  model            : {device.model}")
        print(f"  firmware_version : {device.firmware_version}")
        print(f"  manufacturer     : {device.manufacturer}")
        print(f"  has_tank         : {device.has_tank}")

        # ── Status ────────────────────────────────────────────────
        hr("Status")
        print(f"  operation_status   : {device.operation_status.name}")
        print(f"  mode               : {device.mode.name} ({ExtendedOperationMode(device.mode).value})")
        print(f"  device_mode_status : {device.device_mode_status.name}  (NORMAL=0, DEFROST=1)")
        print(f"  current_action     : {device.current_action.name}")
        print(f"  current_direction  : {device.current_direction.name}")
        print(f"  temperature_outdoor: {device.temperature_outdoor}°C")
        print(f"  pump_duty          : {device.pump_duty.name}")
        print(f"  is_on_error        : {device.is_on_error}")
        if device.current_error:
            print(f"  current_error      : [{device.current_error.error_code}] {device.current_error.error_message}")

        # ── Controls ──────────────────────────────────────────────
        hr("Controls / toggles")
        print(f"  quiet_mode     : {device.quiet_mode.name}  (OFF/LEVEL1/LEVEL2/LEVEL3)")
        print(f"  force_dhw      : {device.force_dhw.name}")
        print(f"  force_heater   : {device.force_heater.name}")
        print(f"  holiday_timer  : {device.holiday_timer.name}")
        print(f"  powerful_time  : {device.powerful_time.name}  (OFF/30MIN/60MIN/90MIN)")
        print(f"  special_status : {device.special_status.name if device.special_status else 'None'}  (ECO/COMFORT)")
        print(f"  support_special_status: {device.support_special_status}")

        # ── Tank ──────────────────────────────────────────────────
        hr("Tank")
        if device.has_tank and device.tank:
            t = device.tank
            print(f"  operation_status  : {t.operation_status.name}")
            print(f"  temperature       : {t.temperature}°C  (current)")
            print(f"  target_temperature: {t.target_temperature}°C")
            print(f"  heat_min          : {t.heat_min}°C")
            print(f"  heat_max          : {t.heat_max}°C")
        else:
            print("  No tank on this device")

        # ── Zones ─────────────────────────────────────────────────
        hr(f"Zones ({len(device.zones)})")
        for zone_id, zone in device.zones.items():
            print(f"\n  Zone {zone_id}: {zone.name}")
            print(f"    type                  : {zone.type}")
            print(f"    operation_status      : {zone.operation_status.name}")
            print(f"    temperature (current) : {zone.temperature}°C")
            print(f"    cool_mode             : {zone.cool_mode}")
            print(f"    sensor_mode           : {zone.sensor_mode}")
            print(f"    heat_sensor_mode      : {zone.heat_sensor_mode}")
            print(f"    cool_sensor_mode      : {zone.cool_sensor_mode}")
            print(f"    supports_set_temperature : {zone.supports_set_temperature}")
            print(f"    supports_special_status  : {zone.supports_special_status}")
            print(f"    heat_target_temperature  : {zone.heat_target_temperature}°C")
            print(f"    cool_target_temperature  : {zone.cool_target_temperature}°C")
            print(f"    heat_min / heat_max      : {zone.heat_min} / {zone.heat_max}")
            print(f"    cool_min / cool_max      : {zone.cool_min} / {zone.cool_max}")
            if zone.supports_special_status:
                print(f"    eco  modifiers (heat/cool): {zone.eco.heat} / {zone.eco.cool}")
                print(f"    comfort modifiers         : {zone.comfort.heat} / {zone.comfort.cool}")

        # ── What the integration is MISSING ───────────────────────
        hr("Gap analysis vs current integration")

        missing = []

        # tank_temperature: accessed via device.tank.temperature, not device.tank_temperature
        if device.has_tank and device.tank:
            missing.append(
                f"  [SENSOR] Tank temperature ({device.tank.temperature}°C) — "
                "sensor.py uses hasattr(device, 'tank_temperature') which is always False. "
                "Correct access: device.tank.temperature"
            )

        # DeviceAction.HEATING_WATER not surfaced in climate entity
        missing.append(
            "  [CLIMATE] DeviceAction.HEATING_WATER not mapped — "
            "when heat pump heats DHW, current_action returns HEATING_WATER "
            "but convert_aquarea_action_to_hvac_action() falls through to IDLE. "
            "Consider surfacing in water_heater entity instead."
        )

        # Switches that exist in library but dead code in switch.py
        missing.append(
            "  [SWITCH] force_dhw / force_heater / holiday_timer — "
            "all exist on Device directly (device.force_dhw etc) but switch.py "
            "guards them with hasattr(device, 'has_force_dhw') which is never True. "
            "Should use hasattr(device, 'force_dhw') instead."
        )

        # Zone sensors using wrong iteration
        missing.append(
            "  [SENSOR] Zone temperatures — sensor.py iterates getattr(device, 'zones', []) "
            "but device.zones is a dict[int, DeviceZone]. Should iterate device.zones.values() "
            "and access zone.temperature directly."
        )

        # current_error as sensor
        missing.append(
            "  [SENSOR] current_error — device.current_error.error_code / error_message "
            "not surfaced. sensor.py checks hasattr(device, 'error_code') which is False. "
            "The binary_sensor covers is_on_error but error code/message not shown."
        )

        for m in missing:
            print(m)

        hr("Done")


if __name__ == "__main__":
    asyncio.run(main())
