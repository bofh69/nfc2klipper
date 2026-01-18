<!--
SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![REUSE status](https://api.reuse.software/badge/github.com/bofh69/nfc2klipper)](https://api.reuse.software/info/github.com/bofh69/nfc2klipper)
![GitHub Workflow Status](https://github.com/bofh69/nfc2klipper/actions/workflows/pylint.yml/badge.svg)


# nfc2klipper

<p>

nfc2klipper is a tiny part of a spool/filament management system.
It makes sure [Klipper](https://www.klipper3d.org/) knows which spool,
and filament, that is loaded so the usage can be tracked in
[Spoolman](https://github.com/donkie/Spoolman).

New spools with [OpenTag3D](https://opentag3d.info/) or
[OpenPrintTag](https://openprinttag.org/) NFC tags are automatically
added to Spoolman's database. You can also add your own tag to a new
spool, connect it to the spool in Spoolman and then the printer will
track its usage without any further change.

[spoolman2slicer](https://github.com/bofh69/spoolman2slicer) is another
optional part of the system. It generates slicer configuration files,
making it easy to make the printer pause the print if the wrong filament
is loaded.

[spool2klipper](https://github.com/bofh69/spool2klipper) is my last optional
program. It can transfer all of Spoolman's info about a spool/filament to Klipper
whenever the spool is changed (either with a gcode, nfc2klipper or via
the printer's web page) so other gcode macros can use it for things like
preheating the bed to the right temperature, warming the nozzle to
the right temperature and so on.

<img align="right" src="images/nfc_reader_on_voron.jpg" width="200" height="158" alt="NFC Reader on Voron" />
</p>

- Table of Contents
  - [Prepare for running nfc2klipper](#prepare-for-running-nfc2klipper)
  - [Preparing an NFC reader](#preparing-an-nfc-reader)
    - [Using PN532](#using-pn532)
      - [PN532 bug in the nfcpy module](#pn532-bug-in-the-nfcpy-module)
    - [Using PN5180](#using-pn5180)
  - [Preparing klipper](#preparing-klipper)
  - [Preparing the slicer](#preparing-the-slicer)
  - [Preparing tags](#preparing-tags)
    - [Using tag's id](#using-tags-id)
    - [SPOOL & FILAMENT in tags](#spool--filament-in-tags)
      - [Write tags with the web server](#write-tags-with-the-web-server)
      - [Write with an app](#write-with-an-app)
      - [Write with console application](#write-with-console-application)
  - [Run automatically with systemd](#run-automatically-with-systemd)
  - [Automatic upgrades with moonraker](#automatic-upgrades-with-moonraker)
  - [Use with Happy-Hare](#use-with-happy-hare)
  - [Use with Prusa's OpenPrintTag tags](#use-with-prusas-openprinttag-tags)
  - [Use with OpenTag3D tags](#use-with-opentag3d-tags)
  - [Related projects](#related-projects)
  - [Developer info](#developer-info)


## Prepare for running nfc2klipper

Install python >= 3.10.
On some distributions you may need to install "python3-venv" or
something similar.

In the cloned repository's dir run:
```sh
python3 -m venv venv
venv/bin/pip3 install -r requirements.txt
```

Copy and update `nfc2klipper.cfg` to `~/.config/nfc2klipper/nfc2klipper.cfg`.

You can specify a custom configuration directory using the `-c` or `--config-dir` command-line option:
```sh
venv/bin/python3 nfc2klipper_backend.py -c /path/to/config/directory
```

## Preparing Spoolman

nfc2klipper can use RFID/NFC tags containing its own format, but
it can also use tags in other formats, like tags for
Filaman, OpenTag3D, OpenPrintTag and probably many others.

For it to be able to use other tag formats, the spool needs to have
an extra `nfc_id` field.
Add it in Spoolman under settings -> extra fields -> spool.
Set the "key" to `nfc_id`, the "type" should be `text` and the "name"
can be anything you want.


## Preparing an NFC reader

At least two different readers can be used:

- PN532, using [nfcpy](https://nfcpy.readthedocs.io/en/latest/), connected via UART/serial.
- PN5180 using [PN5180-Tagomatic](https://github.com/bofh69/pn5180-tagomatic), connected via USB.

nfcpy supports many other readers too, which probably works fine, but
I've not tested them.

### Using PN532

PN532 is well tested, but it can't read NFC type-V tags,
used by OpenPrintTag. If you want to use those,
use a PN5180 reader instead.

I use a "Elechouse PN532 NFC RFID Module V3" board connected via UART
to the Raspberry Pi where nfc2klipper is running.

Many pages suggest connecting its VCC pin to 5V on the RPi. Don't!
It can run from 3.3V and then it won't risk slowly destroying the RPi's
GPIO pins.


See [here](https://learn.adafruit.com/adafruit-nfc-rfid-on-raspberry-pi/pi-serial-port)
for how to configure a Raspberry Pi for it (but change VCC pin...).

Run `sudo rpi-update` to avoid problems with older firmware on the RPi.

There is a model for attaching it to the printer
[here](https://www.printables.com/model/798929-elechouse-pn532-v3-nfc-holder-for-voron-for-spoolm).


#### PN532 bug in the nfcpy module

When running it on a Raspberry Pi's mini-uart (ttyS0 as device), it works fine.
When using the other UART (ttyAMA0), I can only run the programs once.
I have to power cycle the PN532 to get it to work again. Just rebooting
the RPi doesn't help.

This is due to a bug in nfcpy (version 1.0.4), see
[issue #186](https://github.com/nfcpy/nfcpy/issues/186).

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

### Using PN5180

The PN5180 reader chip is much better than PN532, it can communicate
via more protocols. The driver however is limited right now and not as
well tested as nfcpy.

The driver can only read NFC type 2 (NTAG 21x, Mifare Classic) and
NFC Type V tags (used by OpenPrintTag). That is enough for the tags I've used.

The PN5180 is connected to a Raspberry Pi Pico Zero card and from there to
the computer via USB. See the link above for how to put it together, including
a 3D printed case for it.

In the nfc2klipper.cfg file's "nfc" section, use "pn5180" as
"nfc-reader" and set "nfc-device" to
"/dev/serial/by-id/usb-Arduino_RaspberryPi_Pico_053444501C6F7A80-if00",
(but obviously change the serial number part to yours).

One thing that isn't supported, is writing to tags. The driver supports it,
but not nfc2klipper. That was the first method used by nfc2klipper,
but the newer method of storing the tags' ID number in Spoolman almost
always a better method.


## Preparing klipper

When a tag has been read, it will send these gcodes to Klipper:

* `SET_ACTIVE_FILAMENT ID=n1`
* `SET_ACTIVE_SPOOL ID=n2`

This can be be changed in nfc2klipper's configuration,
see the `macros` section in the config file.

See [klipper-spoolman.cfg](klipper-spoolman.cfg) for the klipper
config for them. Klipper must also have a `[save-variables]` section
in its config, see
[Klipper's documentation](https://www.klipper3d.org/Config_Reference.html#save_variables)
for those macros to work properly.


## Preparing the slicer

For every filament, add a custom start gcode that calls:

`ASSERT_ACTIVE_FILAMENT ID=<id>`

where `<id>` is its filament id in Spoolman.

This can be done automatically by using [spoolman2slicer](https://github.com/bofh69/spoolman2slicer).


## Preparing tags

If nfc2klipper reads a new OpenTag3D or OpenPrintTag tag, it will
automatically create a new spool in Spoolman and connect it with the tag.

If you have your own tags (or the spool comes with another), you can either
[write custom data](#spool--filament-in-tags) to them, or
[connect their ID](#using-tags-id) to the Spool in Spoolman.

The second method allows nfc2klipper to be used with
tags without changing their content, making interop with other
systems easier. It is now the recommended way of using nfc2klipper.

## Runing the backend

Run `nfc2klipper_backend.py`.

See further down for running it as a systemd service.

`nfc2klipper.py` is only there for backwards compability and making
development easier.

### Using tag's id

The latest read tags' identifier can be set in the Spool record in Spoolman via the web
server's page, click on the "Set in Spoolman" button for the spool that's loaded.

That way the tag will be connected to that spool without having to change its data.


### SPOOL & FILAMENT in tags

The tags should contain an NDEF record with a text block like this:
```
SPOOL:3
FILAMENT:2
```

The numbers are the id numbers that will be sent to the macros in
klipper via the [Moonraker](https://github.com/Arksine/moonraker) API.

#### Write tags with the web server

`nfc2klipper_api.py` can be run as a (WSGI) web server with for example
[Gunicorn](https://gunicorn.org). It will then serve a web page for
writing to the tags or setting the spool's id in Spoolman, like FilaMan does.

Please note that nfc2klipper does not implement any authentication, so
only run this on secure networks, or add reverse proxy (like nginx)
with some authentication. Follow the link above for Gunicorn's
documentation.

To run it with **low security**;
```sh
gunicorn --bind localhost:5001 nfc2klipper_api:app
```

Change localhost to your computer's hostname (or IP-address) if it should server
the whole network.

One can also start the file directly, but then it uses a development
web server with **no security** at all (if enabled in the configuration file).

The program uses the configuration file (`~/.config/nfc2klipper/nfc2klipper.cfg`) for
getting the unix domain name used to communicate with the `nfc2klipper_backend.py`.

The web page lists the current spools in Spoolman.

By pressing the "Write" button, its info is written to the nfc/rfid tag.

By pressing the "Set in Spoolman" button, the tag's id is stored in
an extra field for the spool in Spoolman. This is the recommended method.


#### Write with an app

There is an Android app, [Spoolman Companion](https://github.com/V-aruu/SpoolCompanion),
for writing to the tags.


## Run automatically with systemd

Copy `nfc2klipper_backend.service` to `/etc/systemd/system`, then run:

```sh
sudo systemctl start nfc2klipper_backend
sudo systemctl enable nfc2klipper_backend
```

To see its status, run:
```sh
sudo systemctl status nfc2klipper_backend
```

To run the web server, copy `nfc2klipper_api.service` to
`/etc/systemd/system`, then run:

```sh
sudo systemctl start nfc2klipper_api
sudo systemctl enable nfc2klipper_api
```

To see its status, run:
```sh
sudo systemctl status nfc2klipper_api
```

## Automatic upgrades with moonraker

Moonraker can be configured to help upgrade nfc2klipper.

Copy the `moonraker-nfc2klipper.cfg` file to the same dir as where
`moonraker.conf` is. Include the config file by adding:
```toml
[include moonraker-nfc2klipper.cfg]
```

## Use with Happy-Hare
(This is completly untested by me, please let me know if it works or not)

Change the `setting_gcode` value in nfc2klipper.cfg to:
```gcode
MMU_GATE_MAP NEXT_SPOOLID={spool}
```
See Happy-Hare's [documentation](https://github.com/CooperGerman/Happy-Hare/wiki/Spoolman-Support#auto-setting-with-rfid-reader)

## Use with Prusa's OpenPrintTag tags

[OpenPrintTag](https://openprinttag.org/) is a format containing info
about the spool, its filament and the vendor.

Unfortunatly OpenPrintTag uses NFC Type-V tags that can't be read by
PN532 readers. A PN5180 reader is needed for them.

When nfc2klipper reads an OpenPrintTag, it first checks if its ID is already in
Spoolman. If so, that spool is used. This means that if a tag is reused, its old
spool should first be archived in Spoolman (or simply empty its nfc_id field first),
otherwise the tag will still match the old Spool in spoolman.

If the ID can't be found in Spoolman, the tags' fields are used to create
(if needed), a new Vendor, Filament and Spool in Spoolman. The Spool's 'nfc_id' extra
field will be filled with the tag's ID.

The filaments name is taken from the tags "material_name" field
(Prusament uses names like "PLA Lipstick Red"), but what fields are used
can be changed in the configuration file.

There is a default mapping between the tag's fields and fields in Spoolman,
but that can be changed with the configuration file. Fields that are not part
of the standard fields in Spoolman can be put in extra fields. They need to be
configured first in Spoolman.

See Spoolman's API documentation [here](https://donkie.github.io/Spoolman/)
to see the names of the fields in Spoolman.

You can also add extra fields in Spoolman for saving more of the data
from the OpenPrintTag tags.

See the log file for the field names when a new OpenPrintTag tag is read.


## Use with OpenTag3D tags
(This is not tested with real tags. Please open an issue if it works or not).

[OpenTag3d](https://opentag3d.info/) is a tag format containing info about the spool and filament.
nfc2klipper can read the format (v0.12, possibly later), create vendor,
filament and spool records in Spoolman from the tag's data.

When nfc2klipper reads an OpenTag3D, it first checks if its ID is already in
Spoolman. If so, that spool is used. This means that if a tag is reused, its old
spool should first be archived in Spoolman (or simply empty its nfc_id field first),
otherwise the tag will still match the old Spool in spoolman.

The Filament's name is by default generated from the tag's `material_base` `material_mod` and `color_name` fields.
That can be changed in the configuration file.

The created spools and filaments in spoolman gets the data from the tag.
Which tag's data field should end up in which spoolman field is also configurable.

See Spoolman's API documentation [here](https://donkie.github.io/Spoolman/) to see the names of the fields in Spoolman.
You can also add extra fields in Spoolman for saving more of the data from the OpenTag3D tags.


## Related projects

* [FilaMan](https://www.filaman.app/) - a filament management system.
* [esp_to_spoolman](https://github.com/dimbas80/esp_to_spoolman) - like nfc2klipper, but running on an ESP32.
* [spool2klipper](https://github.com/bofh69/spool2klipper) - to set the filament id (and other data) when the spool id is changed.
* [spoolman2slicer](https://github.com/bofh69/spoolman2slicer) - create filament config from Spoolman.
* [OpenTag3d](https://opentag3d.info/) tag format.

## Developer info

Pull requests are happily accepted, but before making one make sure
the code is formatted correctly and linted without errors.

Format the code by running `make fmt` and lint it with `make lint`.

Python types are used. Check them with `make typecheck`

Add copyright info in SPDX format in new files and check that it is correct with `make reuse`.
