<!--
SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![REUSE status](https://api.reuse.software/badge/github.com/bofh69/nfc2klipper)](https://api.reuse.software/info/github.com/bofh69/nfc2klipper)
![GitHub Workflow Status](https://github.com/bofh69/nfc2klipper/actions/workflows/pylint.yml/badge.svg)


# nfc2klipper

Set loaded spool &amp; filament in klipper from NFC/RFID tags.

## Prepare for running nfc2klipper

In the cloned repository's dir run:
```sh
virtualenv venv
venv/bin/pip3 install -r requirements.txt
```

Copy and update the `nfc2klipper.cfg` to `~/.config/nfc2klipper/nfc2klipper.cfg`.

## Preparing an NFC reader

I use a PN532 based reader (Elechouse PN532 NFC RFID Module V3, if you
want to use the same) connected via UART to the raspberry pi where this
program is running.


Many pages suggest connecting its VCC pin to 5V on the RPi. Don't!
It can run from 3.3V and then it won't risk slowly destroying the RPi's
GPIO pins.


See [here](https://learn.adafruit.com/adafruit-nfc-rfid-on-raspberry-pi/pi-serial-port)
for how to configure a raspberry pi for it (but change VCC pin...).

Run `sudo rpi-update` to avoid problems with older firmware on the pi.

There is a model for attaching it to the printer
[here](https://www.printables.com/model/798929-elechouse-pn532-v3-nfc-holder-for-voron-for-spoolm).


### PN532 bug in the nfcpy module

When running it on a raspberry pi's mini-uart (ttyS0 as device), it works fine.
When using the other UART (ttyAMA0), I can only run the programs once.
I have to power cycle the PN532 to get them to run again. Just rebooting
the pi doesn't help.

This seems to be due to a bug in nfcpy (version 1.0.4),
see (https://github.com/nfcpy/nfcpy/issues/186).

A workaround that works for me is to change
`venv/lib/python3.*/site-packages/nfc/clf/pn532.py`
around line 390, from:

```python
        change_baudrate = True  # try higher speeds
```

to:

```python
        change_baudrate = False  # try higher speeds
```

There is an included patch file that can be applied:
```sh
patch -p6 venv/lib/python3.*/site-packages/nfc/clf/pn532.py < pn532.py.patch
```


## Preparing klipper

When a tag has been read, it will send these gcodes to Klipper:

* `SET_ACTIVE_FILAMENT ID=n1`
* `SET_ACTIVE_SPOOL ID=n2`


See [klipper-spoolman.cfg](klipper-spoolman.cfg) for the klipper
config for them. Klipper must also have a `[save-variables]` section
in its config, see
[Klipper's documentation](https://www.klipper3d.org/Config_Reference.html#save_variables).


## Preparing the slicer

For every filament, add a custom start gcode that calls:

`ASSERT_ACTIVE_FILAMENT ID=<id>`

where `<id>` is its filament id in Spoolman.

This can be done automatically by using [spoolman2slicer](https://github.com/bofh69/spoolman2slicer).


## Preparing tags

The tags should contain an NDEF record with a text block like this:
```
SPOOL:3
FILAMENT:2
```

The numbers are the id numbers that will be sent to the macros in
klipper via the [Moonraker](https://github.com/Arksine/moonraker) API.

### Write tags with the **extperimental** web server

It is possible to enable an **experimental** web server in `nfc2klipper.py`.
It will then serve a web page for writing to the tags.
The default address will be `http://mainsailos.local:5001/`,
where `mainsailos.local` should be replaced with the computer's name (or IP address).

The program uses a development web server with **no security** at all so it
shouldn't be run if the computer is running on an untrusted network.

The program has a configuration file (`~/.config/nfc2klipper/nfc2klipper.cfg`) for
enabling the web server, setting the port number, addresses to moonraker
and mainsail, the webserver's address and NFC device to use.


### Write with an app

There is an Android app, [Spoolman Companion](https://github.com/V-aruu/SpoolCompanion), for writing
to the tags.

### Write with console application

The `write_tags.py` program fetches Spoolman's spools, shows a simple
text interface where the spool can be chosen, and when pressing return,
writes to the tag.

Use the `write_tag` script to stop the nfc2klipper service, run the
`write_tags.py` program and then start the service again after.



## Run automaticly with systemd

Copy nfc2klippper.service to `/etc/systemd/system`, then run:

```sh
sudo systemctl start nfc2klipper
sudo systemctl enable nfc2klipper
```

To see its status, run:
```sh
sudo systemctl status nfc2klipper
```

## Automatic upgrades with moonraker

Moonraker can be configured to help upgrade nfc2klipper.

Copy the the `moonraker-nfc2klipper.cfg` file to the same dir as where
`moonraker.conf` is. Include the config file by adding:
```toml
[include moonraker-nfc2klipper.cfg]
```

## Developer info

Pull requests are happily accepted, but before making one make sure
the code is formatted with black and passes pylint without errors.

The code can be formatted by running `make fmt` and checked with pylint
with `make lint`.
