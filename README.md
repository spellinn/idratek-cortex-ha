# Idratek Cortex for Home Assistant

A native Home Assistant custom integration (domain `idratek_cortex`) for the Idratek Cortex Web API. It replaces the earlier external REST bridge container. Everything runs inside Home Assistant, so there is no separate service, no Key Vault and no pushed pseudo-states: entities are real registry entities with unique IDs, devices and areas.

Built against the Home Assistant developer documentation (Building integrations, published 16 October 2026) and tested on Home Assistant 2026.10.2.

## Supported objects

| Cortex type | Home Assistant | State port | On / Off input ports | Notes |
|---|---|---|---|---|
| IdratekDimmer1 | light (brightness) | 0 | 2 / 3 | Level read from port 1 (0-100), written to port 5 |
| Light, HomeEasyLight | light (on/off) | 15 | 5 / 6 | Port 98 (RF association) is ignored |
| OnOffLoad | switch (outlet) | 16 | 1 / 2 | Port 17 is inverted and not used |
| Room | binary_sensor (occupancy) | 2 (occupied), 8 (delayed occupied) | read only | Port 8 is the delayed output and is a separate entity |
| Motion | binary_sensor (motion) | 0 | read only | Long motion (3) and fault (99) are not read, to limit polling |
| Door | binary_sensor (door) | 2 | read only | On means open; ports 0 and 1 are associations |
| HVAC | climate | demand ports 17 (heat) and 18 (cool) | mode via the `HVACMode` property (0 Off, 1 Heat, 2 Cool, 3 Auto) | Room temp port 0, setpoint out 46 (cool 47), temporary setpoint in 31 (cool 32) |

Temperatures are plain degrees Celsius (for example 22.78), not tenths. A cooling setpoint of -1000 means cooling is disabled, so only Off and Heat are offered.

## Install

1. Copy `custom_components/idratek_cortex` into `<config>/custom_components/` (or add this repository to HACS as a custom repository).
2. Restart Home Assistant.
3. Settings, Devices and services, Add integration, Idratek Cortex. Enter host, port and the Web API username and password. The connection is tested before the entry is created.

Cortex prerequisites: Web Server and Cortex Mobile licences, the Web Server object enabled, a user authorised for the Web API, and each object to expose set to allow viewing, control and Web API.

## Instant updates from Cortex (recommended)

Polling defaults to 60 seconds (option range 15 to 900). For immediate updates, Cortex calls back into Home Assistant using its Web API Client object. The integration options page (Settings, Devices and services, Idratek Cortex, Configure) lists the exact addresses to paste into Cortex: the address you are browsing with, your configured internal URL, and the IP address. Cortex is a Windows application and may not resolve `.local` names, so use the IP address entry if a name fails.

In Cortex (steps from the Cortex help, "Web API Client Object"):

1. Add a Web API Client object (Cortex Logic, Logic Only) and open it.
2. Tick Allow sending of messages. Without it, connections cannot trigger the entries.
3. Choose Add and fill in the Request tab:
   - Description: a unique name, for example `HA Porch occupied`. Cortex names the connection ports after it.
   - HTTP method: `GET` (`POST` also works).
   - ContentType: `application/json`.
   - URL: the address from the options page with nothing added.
   - URL Key List: add the keys `id`, `port` and `value` (see below).
   - Leave Enable basic authentication unticked; the webhook is limited to your local network.
4. Use Test Send. The Raw Response tab shows the substituted URL, and Home Assistant should answer with an empty successful reply.
5. Open the object you want pushed and connect its output port to the entry's `Send` event port, using Filter Global and Object Web API Client.
6. Repeat for each object and port. The Web API Client cannot tell the receiver which object called it, so every object and port needs its own entry.

### Value-carrying callbacks (v2.2.0)

The Cortex API Client supports tags in URL Key List values. Right-click the Value box, choose Insert Tag, and pick the object's output port. Use the `=?0` form so Cortex sends an integer (0 or 100).

| Key | Value |
|---|---|
| `id` | the object IDNumber, typed as a number |
| `port` | the output port number, typed as a number |
| `value` | a tag such as `<Porch.Occupied state output=?0>` |

Home Assistant applies the pushed value immediately, then reads the port from Cortex about 2 seconds later and keeps whatever Cortex reports. If the value is missing or cannot be parsed, or the port is not a known output, the object is simply re-read. The options page lists the exact `id`, `port` and tag for every pushable object in your system.

Pushable ports: Room 2 and 8, Motion 0, Door 2, Light and HomeEasyLight 15, OnOffLoad 16, Dimmer 0 and 1. HVAC objects send `id` only, so Home Assistant re-reads the thermostat. Temperatures stay on polling.

Notes:

- Tags are documented for the URL Key List and Parameter List values. They are not confirmed to work inside the URL field itself, so keep the URL plain.
- A tag refers to the object by name. If you rename an object in Cortex, the tag breaks, while the `id` stays stable.
- The older form `?id=<IDNumber>` in the URL, or a JSON body such as `{"Cortex_HAAPI":{"IDNumber":"27"}}`, still works. A push with no `id` refreshes every object.

Cortex needs the Web Server and Cortex Mobile licences, the Web Server object enabled, and each object enabled for viewing, control and Web API (help: "Enabling Object API Access").

## Commands

All requests use HTTP Basic authentication and the `/api/v1/json/...` form of the Cortex Web API. Per the Cortex help ("Cortex API Web"), GET reads and POST changes:

- Read a port: `GET /api/v1/json/Ports/<id>/<port>`.
- Set a port (brightness, setpoint): `POST /api/v1/json/Ports/<id>?<port>=<value>`. POSTing to `/Ports/<id>/<port>` returns HTTP 405, which was the cause of the "GET action required to query port value" error in 2.0.x.
- Set a property (HVAC mode): `POST /api/v1/json/Properties/<id>?HVACMode=<0-3>`.
- Trigger an input port (on, off): `POST /api/v1/json/objects/<name>?<port description>=1`, with the port set form as the fallback.

## Known limitations

- Objects are read once at setup. Reload the integration after adding objects in Cortex.
- HVAC mode is read from the `HVACMode` property; if the controller does not return it, the PaintString prefix (H, C, A, O) is used instead.
- Temperature, humidity, light level, analogue signal, macro, heat zone and AllLight/AllHVAC objects, and fault ports, are documented in the port data but not yet implemented as platforms.
- Climate temperature properties are defined under both the legacy and the `native_` names; the legacy names stop working in Home Assistant 2027.11.
- Command formats follow the Cortex help; confirm each object type against your controller (see Troubleshooting).

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
