#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper."""

import argparse

import nfc
import requests

SPOOL = "SPOOL"
FILAMENT = "FILAMENT"
NDEF_TEXT_TYPE = "urn:nfc:wkt:T"

parser = argparse.ArgumentParser()
# description="Fetches filaments from Spoolman and creates SuperSlicer filament configs.",

parser.add_argument("--version", action="version", version="%(prog)s 0.0.1")

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

parser.add_argument(
    "-u",
    "--url",
    metavar="URL",
    default="http://mainsailos.local",
    help="URL for the moonraker installation",
)

args = parser.parse_args()


def set_spool_and_filament(url: str, spool: int, filament: int):
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

    print(f"Sending spool #{spool}, filament #{filament} to klipper", flush=True)

    commands = {
        "commands": [
            f"SET_ACTIVE_SPOOL ID={spool}",
            f"SET_ACTIVE_FILAMENT ID={filament}",
        ]
    }

    # In case the post fails, we might not know if the server has received
    # it or not, so set them to None:
    set_spool_and_filament.old_spool = None
    set_spool_and_filament.old_filament = None

    try:
        response = requests.post(
            url + "/api/printer/command", timeout=10, json=commands
        )
        if response.status_code != 200:
            raise ValueError(f"Request to moonraker failed: {response}")
    except Exception as ex:  # pylint: disable=W0718
        print(ex)

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


def on_nfc_connect(tag):
    """Handles a read tag"""

    if tag.ndef is None:
        print("The tag doesn't have NDEF records", flush=True)
        return True

    spool, filament = get_data_from_ndef_records(tag.ndef.records)

    if not args.clear:
        if not (spool and filament):
            print("Did not find spool and filament records in tag", flush=True)
    if args.clear or (spool and filament):
        if not spool:
            spool = 0
        if not filament:
            filament = 0
        set_spool_and_filament(args.url, spool, filament)

    # Don't let connect return until the tag is removed:
    return True


if __name__ == "__main__":
    # Open NFC reader. Will throw an exception if it fails.
    clf = nfc.ContactlessFrontend(args.nfc_device)

    if args.clear:
        # Start by unsetting current spool & filament:
        set_spool_and_filament(args.url, 0, 0)

    while True:
        clf.connect(rdwr={"on-connect": on_nfc_connect})
        # No tag connected anymore.
        if args.clear:
            set_spool_and_filament(args.url, 0, 0)
