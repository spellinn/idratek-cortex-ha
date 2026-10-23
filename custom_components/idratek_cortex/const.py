"""Constants and the Cortex port dispatch table for Idratek Cortex."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

DOMAIN = "idratek_cortex"
LOGGER = logging.getLogger(__package__)

MANUFACTURER = "Idratek"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_PORT = 80
DEFAULT_SCAN_INTERVAL = 60  # seconds; webhooks give near-instant updates
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 900
REQUEST_TIMEOUT = 15
MAX_CONCURRENT_REQUESTS = 4

# Cortex convention: -1000 means "not configured / disabled".
DISABLED_SENTINEL = -1000.0

# After a value-carrying push is applied, re-read the object once to confirm.
CONFIRM_DELAY = 2.0  # seconds

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# Object types
TYPE_DIMMER = "IdratekDimmer1"
TYPE_LIGHT = "Light"
TYPE_HOMEEASY_LIGHT = "HomeEasyLight"
TYPE_ONOFFLOAD = "OnOffLoad"
TYPE_HVAC = "HVAC"
TYPE_HEATZONE = "HeatZone"
TYPE_HOUSE = "House"
TYPE_ROOM = "Room"
TYPE_MOTION = "Motion"
TYPE_DOOR = "Door"


@dataclass(frozen=True, slots=True)
class SwitchedPorts:
    """Port numbers for an on/off style object (light, plug)."""

    state: int  # output port whose State is true when on
    on: int  # input port: turn on
    off: int  # input port: turn off
    on_desc: str = "Turn on"  # case-sensitive port description used by named triggers
    off_desc: str = "Turn off"
    level: int | None = None  # ValueOut port holding 0-100 dim level
    set_level: int | None = None  # ValueIn port that sets 0-100 dim level
    set_level_desc: str = "Set Dim Level"


# Verified against the stored port dumps (see README, "Port dispatch table").
DIMMER_PORTS = SwitchedPorts(state=0, on=2, off=3, level=1, set_level=5)
LIGHT_PORTS = SwitchedPorts(state=15, on=5, off=6, on_desc="Turn On", off_desc="Turn Off")
ONOFFLOAD_PORTS = SwitchedPorts(state=16, on=1, off=2)

LIGHT_TYPES: dict[str, SwitchedPorts] = {
    TYPE_DIMMER: DIMMER_PORTS,
    TYPE_LIGHT: LIGHT_PORTS,
    TYPE_HOMEEASY_LIGHT: LIGHT_PORTS,  # identical layout to Light
}
SWITCH_TYPES: dict[str, SwitchedPorts] = {TYPE_ONOFFLOAD: ONOFFLOAD_PORTS}


@dataclass(frozen=True, slots=True)
class HvacPorts:
    """Port numbers for the Cortex HVAC object."""

    room_temp: int = 0  # ValueIn, degrees C (float)
    mode_off: int = 6
    mode_heat: int = 7
    mode_cool: int = 8
    mode_auto: int = 9
    heat_demand: int = 17  # Out, State true while heating
    cool_demand: int = 18  # Out, State true while cooling
    set_heat_setpoint: int = 31  # ValueIn, temporary heating setpoint
    set_cool_setpoint: int = 32  # ValueIn, temporary cooling setpoint
    heat_setpoint: int = 46  # ValueOut
    cool_setpoint: int = 47  # ValueOut, -1000 = cooling disabled
    mode_descriptions: tuple[tuple[int, str], ...] = (
        (6, "Mode Off"),
        (7, "Mode Heating"),
        (8, "Mode Cooling"),
        (9, "Mode Auto"),
    )


HVAC_PORTS = HvacPorts()

# HVAC "HVACMode" property values (Cortex help: Cortex API JSON, Properties).
HVAC_MODE_PROPERTY = "HVACMode"
HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_AUTO = 0, 1, 2, 3

# Ports that the coordinator reads for each object type.
READ_PORTS: dict[str, tuple[int, ...]] = {
    TYPE_DIMMER: (0, 1),
    TYPE_LIGHT: (15,),
    TYPE_HOMEEASY_LIGHT: (15,),
    TYPE_ONOFFLOAD: (16,),
    TYPE_HVAC: (0, 17, 18, 46, 47),
    TYPE_ROOM: (2, 8),  # 2 occupied (raw), 8 delayed occupied
    TYPE_MOTION: (0,),  # 0 motion output
    TYPE_DOOR: (2,),  # 2 door output, true = open
}

# Ports worth pushing from a Cortex Web API Client, with their Cortex descriptions.
# HVAC is intentionally absent: several of its values change together, so use id only.
PUSH_PORTS: dict[str, tuple[tuple[int, str], ...]] = {
    TYPE_ROOM: ((2, "Occupied state output"), (8, "Delayed occupied state output")),
    TYPE_MOTION: ((0, "Output"),),
    TYPE_DOOR: ((2, "Door output state"),),
    TYPE_LIGHT: ((15, "Set On (Output)"),),
    TYPE_HOMEEASY_LIGHT: ((15, "Set On (Output)"),),
    TYPE_ONOFFLOAD: ((16, "Set On (Output)"),),
    TYPE_DIMMER: ((0, "On-Off State (Output)"), (1, "Dim Level (Output)")),
}

SUPPORTED_TYPES = frozenset(READ_PORTS)
