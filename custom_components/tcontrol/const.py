"""Constants for the TControl LT16 integration."""

DOMAIN = "tcontrol"

CONF_CONNECTION_TYPE = "connection_type"
CONF_SERIAL_PORT = "port"
CONF_TCP_HOST = "host"
CONF_TCP_PORT = "tcp_port"
CONF_NUM_CHANNELS = "number_of_channels"

CONNECTION_TYPE_SERIAL = "serial"
CONNECTION_TYPE_TCP = "tcp"

DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_TCP_PORT = 8888
DEFAULT_NUM_CHANNELS = 8

MANUFACTURER = "TControl"
MODEL = "LT16 Controller"
