<!--
SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![REUSE status](https://api.reuse.software/badge/github.com/bofh69/nfc2klipper)](https://api.reuse.software/info/github.com/bofh69/nfc2klipper)
![GitHub Workflow Status](https://github.com/bofh69/nfc2klipper/actions/workflows/pylint.yml/badge.svg)

# nfc2klipper

Set loaded spool &amp; filament in klipper from NFC tags.


## Preparing an NFC reader

I use a PN532 based reader (Elechouse PN532 NFC RFID Module V3, if you
want to use the same) connected via UART to the raspberry pi where this
program is running.


Many pages suggest connecting its VCC pin to 5V on the RPi. Don't!
It can run from 3.3V and then it won't risk destroying the RPi's GPIO pins.


See [here](https://learn.adafruit.com/adafruit-nfc-rfid-on-raspberry-pi/pi-serial-port)
for how to configure a raspberry pi for it.


## Preparing klipper

Klipper should have two gcode macros:

* SET_ACTIVE_FILAMENT ID=n
* SET_ACTIVE_SPOOL ID=n


I use this configuration:
```ini
[gcode_macro SET_ACTIVE_SPOOL]
gcode:
  {% if params.ID %}
    {% set id = params.ID|int %}
    {action_call_remote_method(
       "spoolman_set_active_spool",
       spool_id=id
    )}
  {% else %}
    {action_respond_info("Parameter 'ID' is required")}
  {% endif %}

[gcode_macro SET_ACTIVE_FILAMENT]
variable_active_filament: 0
gcode:
  {% if params.ID %}
    {% set id = params.ID|int %}
    SET_GCODE_VARIABLE MACRO=SET_ACTIVE_FILAMENT VARIABLE=active_filament VALUE={id}
  {% else %}
    {action_respond_info("Parameter 'ID' is required")}
  {% endif %}

[gcode_macro ASSERT_ACTIVE_FILAMENT]
gcode:
  {% if params.ID %}
    {% set id = params.ID|int %}
    {% current_id = printer["gcode_macro set_active_filament"].active_filament %}
    {% if id != current_id %}
      {# TODO: Change to PAUSE & M117 message #}
      {action_raise_error("Wrong filament is loaded, should be " + id)}
    {% endif %}
  {% else %}
    {action_respond_info("Parameter 'ID' is required")}
  {% endif %}
```

## Preparing tags

The tags should contain an NDEF record with a text block like this:
```
SPOOL: 3
FILAMENT: 2
```

The numbers are the id numbers that will be sent to the macros in
klipper via the [Moonraker](https://github.com/Arksine/moonraker) API.


This can be written via NXP's TagWriter on a phone, or better yet,
use the `write_tags.py` program. The later fetches Spoolman's filaments,
shows a simple GUI, press return on the chosen spool and it will be
written to the tag.
