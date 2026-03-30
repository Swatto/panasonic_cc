# Panasonic Comfort Cloud - HomeAssistant Component

> [!WARNING]
> **Unstable / Personal fork** — This is not a stable release. It is maintained for personal use only and is not intended for general consumption. Use at your own risk.

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Integration Usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&style=for-the-badge&logo=home-assistant&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.panasonic_cc.total)](https://analytics.home-assistant.io/)

This is a custom component to allow control of Panasonic Comfort Cloud devices in [HomeAssistant](https://home-assistant.io).

> [!IMPORTANT]
> Before installing this integration, please ensure the following steps have been completed in the Panasonic Comfort Cloud App:
>
> - **Set Up Two-Factor Authentication (2FA):** Complete the entire 2FA setup process.  
> - **Select the SMS Option:** It is crucial to choose the SMS option for 2FA. Failing to do so will result in the error “Missing required parameter: code.”  
>
> For optimal operation, it is also recommended that you use separate accounts for Home Assistant and the Comfort Cloud App.

<p>
    <img src="https://github.com/Swatto/panasonic_cc/raw/master/doc/controls.png" alt="Example controls" style="vertical-align: top;max-width:100%" align="top" />
    <img src="https://github.com/Swatto/panasonic_cc/raw/master/doc/sensors.png" alt="Example sensors" style="vertical-align: top;max-width:100%" align="top" />
    <img src="https://github.com/Swatto/panasonic_cc/raw/master/doc/diagnostics.png" alt="Example diagnostics" style="vertical-align: top;max-width:100%" align="top" />
</p>



## Features

* Climate component for Panasonic airconditioners and heatpumps
* Horizontal swing mode selection
* Sensors for inside and outside temperature (where available)
* Switch for toggling Nanoe mode (where available)
* Switch for toggling ECONAVI mode (where available)
* Switch for toggling AI ECO mode (where available)
* Daily energy sensor (optional)
* Current Power sensor (Calculated from energy reading)
* Zone controls (where available)

## Installation

### HACS (recommended)
1. [Install HACS](https://hacs.xyz/docs/setup/download), if you did not already
2. [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sockless-coding&repository=panasonic_cc&category=integration)
3. Press the Download button
4. Restart Home Assistant
5. [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=panasonic_cc)

### Install manually
Clone or copy this repository and copy the folder 'custom_components/panasonic_cc' into '<homeassistant config>/custom_components/panasonic_cc'

## Configuration

Once installed, the Panasonic Comfort Cloud integration can be configured via the Home Assistant integration interface where it will let you enter your Panasonic ID and Password.

![Setup](https://github.com/Swatto/panasonic_cc/raw/master/doc/setup.png)

After inital setup, the following options are available:

![Setup](https://github.com/Swatto/panasonic_cc/raw/master/doc/configuration.png)

## Development

### Prerequisites

This project uses [uv](https://docs.astral.sh/uv/) for Python tooling.

```bash
uv sync --dev          # install dependencies
uv run pytest tests/   # run unit tests
uv run mypy custom_components/panasonic_cc/ --ignore-missing-imports
```

### Testing in Home Assistant (Docker)

The safest way to test changes against a real device is with a disposable HA instance in Docker.

**1. Start a test instance**

```bash
docker run -d --name ha-test \
  -p 8123:8123 \
  -v ./ha-test-config:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

**2. Copy the integration in**

```bash
docker cp custom_components/panasonic_cc ha-test:/config/custom_components/
docker restart ha-test
```

**3. Configure**

Go to `http://localhost:8123`, complete the HA onboarding, then add the integration via **Settings > Devices & Services > Add Integration > Panasonic Comfort Cloud**. Enter your Panasonic credentials.

**4. Iterate**

When you make code changes, copy and restart:

```bash
docker cp custom_components/panasonic_cc ha-test:/config/custom_components/
docker restart ha-test
```

**5. Cleanup**

```bash
docker stop ha-test && docker rm ha-test
rm -rf ./ha-test-config
```

> [!WARNING]
> **Rate limits:** Panasonic aggressively blocks clients that authenticate too frequently. Space out restarts (a few minutes apart is fine). Never automate restart loops against the real API.

> [!TIP]
> Use **Developer Tools > States** in the HA UI to inspect entity attributes, and **Developer Tools > Services** to test calling entity services (e.g., `switch.turn_on`).

## Known issues

- The authentication process can be fiddly and may require resetting the MFA by logging in / out from the Panasonic app.

## Dependencies

This integration uses the following modules:

- [`aio-panasonic-comfort-cloud`](https://github.com/sockless-coding/aio-panasonic-comfort-cloud): For Panasonic Heatpumps.
- [`aioaquarea`](https://github.com/cjaliaga/aioaquarea): For Panasonic Aquarea devices.





[license-shield]: https://img.shields.io/github/license/Swatto/panasonic_cc.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Swatto/panasonic_cc.svg?style=for-the-badge
[releases]: https://github.com/Swatto/panasonic_cc/releases
