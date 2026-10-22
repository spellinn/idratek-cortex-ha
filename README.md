# Idratek Cortex for Home Assistant

A native Home Assistant custom integration (domain `idratek_cortex`) for the Idratek Cortex Web API. It replaces the earlier external REST bridge container. Everything runs inside Home Assistant, so there is no separate service, no Key Vault and no pushed pseudo-states: entities are real registry entities with unique IDs, devices and areas.

Built against the Home Assistant developer documentation (Building integrations, published 16 October 2026) and tested on Home Assistant 2026.10.2.

## Supported objects

| Cortex type | Home Assistant | State port | On / Off input ports | Notes |
|---|---|---|---|---|
| IdratekDimmer1 | light (brightness) | 0 | 2 / 3 | Level read from port 1 (0-100), written to port 5 |
| Light, HomeEasyLight | light (on/off) | 15 | 5 / 6 | Port 98 (RF association) is ignored |
| OnOffLoad | switch (outlet) | 16 | 1 / 2 | Port 17 is inverted and not used |
| HVAC | climate | 17 / 18 demand | modes 6 Off, 7 Heat, 8 Cool, 9 Auto | Room temp port 0, setpoint out 46 (cool 47), setpoint write 31 (cool 32), mode inferred from the object PaintString prefix (H, C, A, O) |

Temperatures are plain degrees Celsius (for example 22.78), not tenths. A cooling setpoint of -1000 means cooling is disabled, so only Off and Heat are offered.

## Install

1. Copy `custom_components/idratek_cortex` into `<config>/custom_components/` (or add this repository to HACS as a custom repository).
2. Restart Home Assistant.
3. Settings, Devices and services, Add integration, Idratek Cortex. Enter host, port and the Web API username and password. The connection is tested before the entry is created.

Cortex prerequisites: Web Server and Cortex Mobile licences, the Web Server object enabled, a user authorised for the Web API, and each object to expose set to allow viewing, control and Web API.

## Instant updates (optional)

Polling defaults to 60 seconds (option range 15 to 900). For near-instant updates add a Cortex Web API Client entry per object (or per group) that POSTs to the webhook path shown in the integration options (`/api/webhook/idratek_cortex_<entry id>` on your Home Assistant URL). Any POST triggers a refresh; the body is ignored. The webhook is local network only.

## Commands

Lights, switches and HVAC modes use the documented named trigger `POST /api/v1/json/objects/<name>?<port description>=1`, falling back to writing 1 to the port on error. Dimmer brightness and HVAC setpoints write `{"CortexAPI":{"PortEvent":{"Value":"<n>"}}}` to `/api/v1/json/Ports/<id>/<port>`.

## Known limitations

- Objects are read once at setup. Reload the integration after adding objects in Cortex.
- The HVAC mode is inferred from PaintString because Cortex has no mode output port.
- Sensors, motion, door, room, macro and AllLight/AllHVAC objects are documented in the port data but not yet implemented as platforms.
- Home Assistant 2026.10 still reads the legacy climate temperature properties, while the current documentation uses the `native_` names (legacy names stop working in 2027.11). Both are defined.
- Command semantics and the Objects.json response shape were written from the stored port dumps and the integration guide; confirm against the live controller (see Troubleshooting).

## Troubleshooting

Enable debug logging for `custom_components.idratek_cortex`, or download diagnostics from the integration page (credentials and host are redacted). If a command appears to succeed but nothing changes, check the port description spelling in the object port list: Light uses "Turn On", dimmer and OnOffLoad use "Turn on".

## Development

```
pip install homeassistant pytest-homeassistant-custom-component
pytest
```

## Install with HACS

1. HACS, menu, Custom repositories, add `https://github.com/spellinn/idratek-cortex-ha` with category Integration.
2. Download Idratek Cortex, restart Home Assistant, then add the integration from Settings, Devices and services.

The integration protocol and port mapping are based on the [HAAPICortex guide](https://github.com/JonaZ80/HAAPICortex).
