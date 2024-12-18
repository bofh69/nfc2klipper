#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags. """

import logging
import threading
import os

from flask import Flask, render_template
import json5

from lib.moonraker_web_client import MoonrakerWebClient
from lib.nfc_handler import NfcHandler
from lib.spoolman_client import SpoolmanClient

SPOOL = "SPOOL"
FILAMENT = "FILAMENT"
NDEF_TEXT_TYPE = "urn:nfc:wkt:T"

script_dir = os.path.dirname(__file__)
cfg_filename = os.path.join(os.path.expanduser("~"), "nfc2klipper-config.json5")
with open(cfg_filename, "r", encoding="utf-8") as fp:
    args = json5.load(fp)

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s: %(message)s"
)

spoolman = SpoolmanClient(args["spoolman-url"])
moonraker = MoonrakerWebClient(args["moonraker-url"])
nfc_handler = NfcHandler(args["nfc-device"])


app = Flask(__name__)


def set_spool_and_filament(spool: int, filament: int):
    """Calls moonraker with the current spool & filament"""

    if "old_spool" not in set_spool_and_filament.__dict__:
        set_spool_and_filament.old_spool = None
        set_spool_and_filament.old_filament = None

    if (
        set_spool_and_filament.old_spool == spool
        and set_spool_and_filament.old_filament == filament
    ):
        app.logger.info("Read same spool & filament")
        return

    app.logger.info("Sending spool #%s, filament #%s to klipper", spool, filament)

    # In case the post fails, we might not know if the server has received
    # it or not, so set them to None:
    set_spool_and_filament.old_spool = None
    set_spool_and_filament.old_filament = None

    try:
        moonraker.set_spool_and_filament(spool, filament)
    except Exception as ex:  # pylint: disable=W0718
        app.logger.error(ex)
        return

    set_spool_and_filament.old_spool = spool
    set_spool_and_filament.old_filament = filament


@app.route("/w/<int:spool>/<int:filament>")
def write_tag(spool, filament):
    """
    The web-api to write the spool & filament data to NFC/RFID tag
    """
    app.logger.info("  write spool=%s, filament=%s", spool, filament)
    if nfc_handler.write_to_tag(spool, filament):
        return "OK"
    return ("Failed to write to tag", 502)


@app.route("/")
def index():
    """
    Returns the main index page.
    """
    spools = spoolman.get_spools()

    return render_template("index.html", spools=spools)


def on_nfc_tag_present(spool, filament):
    """Handles a read tag"""

    if not args.get("clear_spool"):
        if not (spool and filament):
            app.logger.info("Did not find spool and filament records in tag")
    if args.get("clear_spool") or (spool and filament):
        if not spool:
            spool = 0
        if not filament:
            filament = 0
        set_spool_and_filament(spool, filament)


def on_nfc_no_tag_present():
    """Called when no tag is present (or tag without data)"""
    if args.get("clear_spool"):
        set_spool_and_filament(0, 0)


if __name__ == "__main__":

    if args.get("clear_spool"):
        # Start by unsetting current spool & filament:
        set_spool_and_filament(0, 0)

    nfc_handler.set_no_tag_present_callback(on_nfc_no_tag_present)
    nfc_handler.set_tag_present_callback(on_nfc_tag_present)

    if not args.get("disable_web_server"):
        print("Starting nfc-handler")
        thread = threading.Thread(target=nfc_handler.run)
        thread.daemon = True
        thread.start()

        print("Starting web server")
        try:
            app.run(args["web_address"], port=args["web_port"])
        except Exception:
            nfc_handler.stop()
            thread.join()
            raise
    else:
        nfc_handler.run()
