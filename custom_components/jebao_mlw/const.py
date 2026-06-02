"""Constants for the Jebao MLW local integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

DOMAIN = "jebao_mlw"

DEFAULT_NAME = "Jebao MLW"
DEFAULT_PORT = 12416
DEFAULT_DISCOVERY_TIMEOUT = 5
DEFAULT_RECONNECT_DELAY = 10
DEFAULT_FEED_DURATION = 10

DISCOVERY_PORT = 12414

CONF_API_SERVER = "api_server"
CONF_DEVICE_ID = "id"
CONF_DISCOVERY_FINGERPRINT = "discovery_fingerprint"
CONF_DISCOVERY_ID = "discovery_id"
CONF_DEVICES = "devices"
CONF_DISCOVERY_TIMEOUT = "discovery_timeout"
CONF_MODEL = "model"
CONF_RECONNECT_DELAY = "reconnect_delay"
CONF_VERSION = "version"

MANUFACTURER = "Jebao"
MODEL_MLW_10 = "MLW-10"

CONFIG_DEVICE_KEYS = {
    CONF_API_SERVER,
    CONF_DEVICE_ID,
    CONF_DISCOVERY_FINGERPRINT,
    CONF_DISCOVERY_ID,
    CONF_HOST,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    CONF_VERSION,
}
