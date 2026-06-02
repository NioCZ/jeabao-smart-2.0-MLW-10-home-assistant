"""Config flow for the Jebao MLW local integration."""

from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .api import (
    JebaoMlwConnectionError,
    async_discover_devices,
    async_validate_device,
    parse_hosts,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_RECONNECT_DELAY,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RECONNECT_DELAY,
    DOMAIN,
)

def _entry_uid(devices: list[dict[str, Any]]) -> str:
    source = ",".join(
        sorted(str(device.get(CONF_DEVICE_ID) or device[CONF_HOST]) for device in devices)
    )
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


class JebaoMlwConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jebao MLW."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow."""

        return JebaoMlwOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            host_value = str(user_input.get(CONF_HOST, "")).strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            name = str(user_input.get(CONF_NAME) or DEFAULT_NAME).strip()

            if host_value:
                hosts = parse_hosts(host_value)
                if not hosts:
                    errors["base"] = "invalid_host"
                else:
                    devices = []
                    for host in hosts:
                        try:
                            await async_validate_device(host, port)
                        except JebaoMlwConnectionError:
                            errors["base"] = "cannot_connect"
                            break
                        devices.append(
                            {
                                CONF_DEVICE_ID: host,
                                CONF_HOST: host,
                                CONF_PORT: port,
                                CONF_NAME: name if len(hosts) == 1 else f"{name} {host}",
                            }
                        )

                    if not errors:
                        devices = self._filter_already_configured(devices)
                        if not devices:
                            return self.async_abort(reason="already_configured")
                        return await self._async_create_entry(devices, name)
            else:
                discovered = await async_discover_devices(self.hass)
                devices = [
                    device.as_config(
                        name=name if len(discovered) == 1 else f"{name} {device.host}",
                        port=port,
                    )
                    for device in discovered
                ]
                devices = self._filter_already_configured(devices)

                if not devices:
                    errors["base"] = "cannot_discover"
                else:
                    return await self._async_create_entry(devices, name)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOST, default=""): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
            errors=errors,
        )

    async def _async_create_entry(self, devices: list[dict[str, Any]], name: str):
        await self.async_set_unique_id(_entry_uid(devices))
        self._abort_if_unique_id_configured()

        title = (
            devices[0].get(CONF_NAME, name)
            if len(devices) == 1
            else f"{name} ({len(devices)} devices)"
        )
        return self.async_create_entry(
            title=title,
            data={
                CONF_DEVICES: devices,
                CONF_RECONNECT_DELAY: DEFAULT_RECONNECT_DELAY,
            },
        )

    def _filter_already_configured(self, devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        configured = set()
        for entry in self._async_current_entries():
            for device in entry.options.get(CONF_DEVICES) or entry.data.get(CONF_DEVICES, []):
                configured.add(str(device.get(CONF_DEVICE_ID) or device.get(CONF_HOST)))
                configured.add(str(device.get(CONF_HOST)))

        return [
            device
            for device in devices
            if str(device.get(CONF_DEVICE_ID) or device.get(CONF_HOST)) not in configured
            and str(device.get(CONF_HOST)) not in configured
        ]


class JebaoMlwOptionsFlow(config_entries.OptionsFlow):
    """Allow editing configured pumps."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage integration options."""

        current_devices = self.config_entry.options.get(CONF_DEVICES) or self.config_entry.data.get(
            CONF_DEVICES, []
        )
        current_hosts = ", ".join(str(device[CONF_HOST]) for device in current_devices)
        current_port = (
            int(current_devices[0].get(CONF_PORT, DEFAULT_PORT))
            if current_devices
            else DEFAULT_PORT
        )
        current_reconnect_delay = int(
            self.config_entry.options.get(
                CONF_RECONNECT_DELAY,
                self.config_entry.data.get(CONF_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY),
            )
        )

        errors: dict[str, str] = {}

        if user_input is not None:
            hosts = parse_hosts(str(user_input.get(CONF_HOST, "")))
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            reconnect_delay = int(
                user_input.get(CONF_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY)
            )

            if not hosts:
                errors["base"] = "invalid_host"
            else:
                device_by_host = {str(device[CONF_HOST]): device for device in current_devices}
                devices = []
                for host in hosts:
                    existing = dict(device_by_host.get(host, {}))
                    existing.update(
                        {
                            CONF_DEVICE_ID: existing.get(CONF_DEVICE_ID) or host,
                            CONF_HOST: host,
                            CONF_PORT: port,
                            CONF_NAME: existing.get(CONF_NAME) or f"{DEFAULT_NAME} {host}",
                        }
                    )
                    devices.append(existing)

                return self.async_create_entry(
                    title="",
                    data={
                        CONF_DEVICES: devices,
                        CONF_RECONNECT_DELAY: reconnect_delay,
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current_hosts): str,
                    vol.Optional(CONF_PORT, default=current_port): int,
                    vol.Optional(
                        CONF_RECONNECT_DELAY, default=current_reconnect_delay
                    ): int,
                }
            ),
            errors=errors,
        )
