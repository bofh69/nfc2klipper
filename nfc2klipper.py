#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper."""

import argparse
import asyncio
import json

import nfc

# import requests

SPOOL = "SPOOL"
FILAMENT = "FILAMENT"
NDEF_TEXT_TYPE = "urn:nfc:wkt:T"
VERSION = "0.0.2"

parser = argparse.ArgumentParser()
# description="Fetches filaments from Spoolman and creates SuperSlicer filament configs.",

parser.add_argument(
    "--version", action="version", version="%(prog)s " + VERSION
)

parser.add_argument(
    "-c",
    "--clear",
    action="store_true",
    help="Clears the spool & filamnet when no tag is present",
)

parser.add_argument(
    "-d",
    "--nfc-device",
    metavar="device",
    default="ttyAMA0",
    help="Which NFC reader to use, see "
    + "https://nfcpy.readthedocs.io/en/latest/topics/get-started.html#open-a-local-device"
    + " for format",
)

# parser.add_argument(
#    "-u",
#    "--url",
#    metavar="URL",
#    default="http://mainsailos.local",
#    help="URL for the moonraker installation",
# )

parser.add_argument(
    "-k",
    "--klipper-uds",
    metavar="PATH",
    default="/tmp/klippy_uds",
    help="Path to Klipper's API socket.",
)


class KlipperConnection:
    """Connection to klipper's API"""

    def __init__(self):
        self.reader = None
        self.writer = None
        self.msg_id = 1

    async def connect(self, path):
        """Connects to the Unix Domain Socket at _path_"""
        (self.reader, self.writer) = await asyncio.open_unix_connection(path)

    async def send(self, method, params):
        """Sends a request to klipper"""
        cmd = {"id": self.msg_id, "method": method, "params": params}
        self.msg_id += 1
        string = json.dumps(cmd, separators=(",", ":"))
        self.writer.write(string.encode() + "\003")
        await self.writer.drain()

    async def send_gcode(self, gcode):
        """Sends a gcode script to klipper"""
        await self.send("gcode/script", {"script": gcode})


async def set_spool_and_filament(
    klipper: KlipperConnection, spool: int, filament: int
):
    """Calls moonraker with the current spool & filament"""

    if "old_spool" not in set_spool_and_filament.__dict__:
        set_spool_and_filament.old_spool = None
        set_spool_and_filament.old_filament = None

    if (
        set_spool_and_filament.old_spool == spool
        and set_spool_and_filament.old_filament == filament
    ):
        print("Read same spool & filament", flush=True)
        return

    print(
        f"Sending spool #{spool}, filament #{filament} to klipper", flush=True
    )

    # In case the post fails, we might not know if the server has received
    # it or not, so set them to None:
    set_spool_and_filament.old_spool = None
    set_spool_and_filament.old_filament = None

    await klipper.send_gcode(
        f"BEEP\nSET_ACTIVE_SPOOL ID={spool}\nSET_ACTIVE_FILAMENT ID={filament}\nBEEP"
    )

    set_spool_and_filament.old_spool = spool
    set_spool_and_filament.old_filament = filament


def get_data_from_ndef_records(records):
    """Find wanted data from the NDEF records.

    >>> import ndef
    >>> record0 = ndef.TextRecord("")
    >>> record1 = ndef.TextRecord("SPOOL:23\\n")
    >>> record2 = ndef.TextRecord("FILAMENT:14\\n")
    >>> record3 = ndef.TextRecord("SPOOL:23\\nFILAMENT:14\\n")
    >>> get_data_from_ndef_records([record0])
    (None, None)
    >>> get_data_from_ndef_records([record3])
    ('23', '14')
    >>> get_data_from_ndef_records([record1])
    ('23', None)
    >>> get_data_from_ndef_records([record2])
    (None, '14')
    >>> get_data_from_ndef_records([record0, record3])
    ('23', '14')
    >>> get_data_from_ndef_records([record3, record0])
    ('23', '14')
    >>> get_data_from_ndef_records([record1, record2])
    ('23', '14')
    >>> get_data_from_ndef_records([record2, record1])
    ('23', '14')
    """

    spool = None
    filament = None

    for record in records:
        if record.type == NDEF_TEXT_TYPE:
            for line in record.text.splitlines():
                line = line.split(":")
                if len(line) == 2:
                    if line[0] == SPOOL:
                        spool = line[1]
                    if line[0] == FILAMENT:
                        filament = line[1]
        else:
            print(f"Read other record: {record}", flush=True)

    return spool, filament


class Main:
    """The main application"""

    def __init__(self, event_loop, args):
        self.event_loop = event_loop
        self.args = args
        self.klipper = KlipperConnection()

    def on_nfc_connect(self, tag):
        """Handles a read tag"""

        if tag.ndef is None:
            print("The tag doesn't have NDEF records", flush=True)
            return True

        spool, filament = get_data_from_ndef_records(tag.ndef.records)

        if not self.args.clear:
            if not (spool and filament):
                print(
                    "Did not find spool and filament records in tag",
                    flush=True,
                )
        if self.args.clear or (spool and filament):
            if not spool:
                spool = 0
            if not filament:
                filament = 0
            future = asyncio.run_coroutine_threadsafe(
                set_spool_and_filament(self.klipper, spool, filament),
                self.event_loop,
            )
            # Wait for completion:
            future.result()

        # Don't let connect return until the tag is removed:
        return True

    def _nfc_connect(self, clf):
        clf.connect(rdwr={"on-connect": self.on_nfc_connect})

    async def run(self):
        """The main async coroutine"""
        await self.klipper.connect(self.args.klipper_uds)

        # Open NFC reader. Will throw an exception if it fails.
        clf = nfc.ContactlessFrontend(self.args.nfc_device)

        if self.args.clear:
            # Start by unsetting current spool & filament:
            set_spool_and_filament(self.klipper, 0, 0)

        while True:
            await asyncio.to_thread(self._nfc_connect, clf)

            # No tag connected anymore.
            if self.args.clear:
                set_spool_and_filament(self.klipper, 0, 0)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    main = Main(loop, parser.parse_args())
    asyncio.run(main.run())
