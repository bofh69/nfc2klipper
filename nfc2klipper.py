#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags. """

import logging
import os
import sys
import shutil
import threading
from pathlib import Path

from flask import Flask, render_template
import toml

from lib.moonraker_web_client import MoonrakerWebClient
from lib.nfc_handler import NfcHandler
from lib.spoolman_client import SpoolmanClient

SPOOL = "SPOOL"
FILAMENT = "FILAMENT"
NDEF_TEXT_TYPE = "urn:nfc:wkt:T"

CFG_DIR = "~/.config/nfc2klipper"

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s: %(message)s"
)

args = None  # pylint: disable=C0103
for path in ["~/nfc2klipper.cfg", CFG_DIR + "/nfc2klipper.cfg"]:
    cfg_filename = os.path.expanduser(path)
    if os.path.exists(cfg_filename):
        with open(cfg_filename, "r", encoding="utf-8") as fp:
            args = toml.load(fp)
            break

if not args:
    print(
        "WARNING: The config file is missing, installing a default version.",
        file=sys.stderr,
    )
    if not os.path.exists(CFG_DIR):
        cfg_dir = os.path.expanduser(CFG_DIR)
        print(f"Creating dir {cfg_dir}", file=sys.stderr)
        Path(cfg_dir).mkdir(parents=True, exist_ok=True)
    script_dir = os.path.dirname(__file__)
    from_filename = os.path.join(script_dir, "nfc2klipper.cfg")
    to_filename = os.path.join(cfg_dir, "nfc2klipper.cfg")
    shutil.copyfile(from_filename, to_filename)
    print(f"Created {to_filename}, please update it", file=sys.stderr)
    sys.exit(1)

spoolman = SpoolmanClient(args["spoolman"]["spoolman-url"])
moonraker = MoonrakerWebClient(args["moonraker"]["moonraker-url"])
nfc_handler = NfcHandler(args["nfc"]["nfc-device"])


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


def should_clear_spool() -> bool:
    """Returns True if the config says the spool should be cleared"""
    if args["moonraker"].get("clear_spool"):
        return True
    return False


def on_nfc_tag_present(spool, filament, identifier):
    """Handles a read tag"""

    if not (spool and filament):
        app.logger.debug("Fetching data from spoolman from tags' id: %s", identifier)
        spool_data = spoolman.get_spool_from_nfc_id(identifier)
        if spool_data:
            spool = spool_data.get("id")
            if "filament" in spool_data:
                filament = spool_data["filament"].get("id")
        else:
            app.logger.info(
                "Did not find spool records in tag nor from its id (%s) in spoolman",
                identifier,
            )
    if spool and filament:
        if not spool:
            spool = 0
        if not filament:
            filament = 0
        set_spool_and_filament(spool, filament)


def on_nfc_no_tag_present():
    """Called when no tag is present (or tag without data)"""
    if should_clear_spool():
        set_spool_and_filament(0, 0)


if __name__ == "__main__":

    if should_clear_spool():
        # Start by unsetting current spool & filament:
        set_spool_and_filament(0, 0)

    nfc_handler.set_no_tag_present_callback(on_nfc_no_tag_present)
    nfc_handler.set_tag_present_callback(on_nfc_tag_present)

    if not args["webserver"].get("disable_web_server"):
        app.logger.info("Starting nfc-handler")
        thread = threading.Thread(target=nfc_handler.run)
        thread.daemon = True
        thread.start()

        app.logger.info("Starting web server")
        try:
            app.run(
                args["webserver"]["web_address"], port=args["webserver"]["web_port"]
            )
        except Exception:
            nfc_handler.stop()
            thread.join()
            raise
    else:
        nfc_handler.run()
