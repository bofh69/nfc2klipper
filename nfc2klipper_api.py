#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Web API service for nfc2klipper."""

import json
import logging
import os
import socket
import sys

from flask import Flask, render_template
import toml

CFG_DIR = "~/.config/nfc2klipper"
SOCKET_PATH = "/tmp/nfc2klipper.sock"

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
        "ERROR: Config file not found. Please run nfc2klipper_backend.py first.",
        file=sys.stderr,
    )
    sys.exit(1)

app = Flask(__name__)


def send_request(request_data):
    """Send a request to the backend via Unix domain socket"""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.sendall(json.dumps(request_data).encode("utf-8"))
        response = client.recv(65536).decode("utf-8")
        client.close()
        return json.loads(response)
    except Exception as ex:  # pylint: disable=W0718
        app.logger.error("Error communicating with backend: %s", ex)
        return {"status": "error", "message": str(ex)}


@app.route("/w/<int:spool>/<int:filament>")
def write_tag(spool, filament):
    """
    The web-api to write the spool & filament data to NFC/RFID tag
    """
    response = send_request({"command": "write_tag", "spool": spool, "filament": filament})
    if response.get("status") == "ok":
        return "OK"
    # Don't expose internal error details to external users
    return ("Failed to write to tag", 502)


@app.route("/set_nfc_id/<int:spool>")
def set_nfc_id(spool):
    """
    The web-api to write the current nfc_id to spool's nfc_id field in Spoolman
    """
    response = send_request({"command": "set_nfc_id", "spool": spool})
    if response.get("status") == "ok":
        return "OK"
    # Don't expose internal error details to external users
    return ("Failed to send nfc_id to Spoolman", 502)


@app.route("/")
def index():
    """
    Returns the main index page.
    """
    spools_response = send_request({"command": "get_spools"})
    state_response = send_request({"command": "get_state"})

    spools = spools_response.get("spools", []) if spools_response.get("status") == "ok" else []
    nfc_id = state_response.get("nfc_id") if state_response.get("status") == "ok" else None
    spool_id = state_response.get("spool_id") if state_response.get("status") == "ok" else None

    if spool_id:
        spool_id = int(spool_id)
    return render_template(
        "index.html", spools=spools, nfc_id=nfc_id, spool_id=spool_id
    )


if __name__ == "__main__":
    app.logger.info("Starting web server")
    app.run(
        args["webserver"]["web_address"], port=args["webserver"]["web_port"]
    )
