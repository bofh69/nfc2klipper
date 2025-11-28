#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "flask==3.0.3",
#   "toml==0.10.2",
# ]
# ///

"""Web API service for nfc2klipper."""

# pylint: disable=duplicate-code

import argparse
import os
import sys
from typing import Any, Dict, Optional, Tuple, Union

from flask import Flask, render_template
from lib.config import Nfc2KlipperConfig
from lib.ipc import IPCClient


Nfc2KlipperConfig.configure_logging()

# Parse command line arguments
# pylint: disable=duplicate-code
parser = argparse.ArgumentParser(description="Web API service for nfc2klipper.")
parser.add_argument(
    "-c",
    "--config-dir",
    metavar="DIR",
    default=None,
    help=f"Configuration directory (default: {Nfc2KlipperConfig.CFG_DIR})",
)
parsed_args = parser.parse_args()

args: Optional[Dict[str, Any]] = Nfc2KlipperConfig.get_config(parsed_args.config_dir)
# pylint: enable=duplicate-code

if not args:
    print(
        "ERROR: Config file not found. Please run nfc2klipper_backend.py first.",
        file=sys.stderr,
    )
    sys.exit(1)

# Get socket path from config, with fallback to default
socket_path: str = args.get("webserver", {}).get(
    "socket_path", Nfc2KlipperConfig.DEFAULT_SOCKET_PATH
)
socket_path = os.path.expanduser(socket_path)

# Create IPC client
ipc_client: IPCClient = IPCClient(socket_path)

app: Flask = Flask(__name__)


@app.route("/w/<int:spool>/<int:filament>")
def write_tag(spool: int, filament: int) -> Union[str, Tuple[str, int]]:
    """
    The web-api to write the spool & filament data to NFC/RFID tag
    """
    response: Dict[str, Any] = ipc_client.send_request(
        {"command": "write_tag", "spool": spool, "filament": filament}
    )
    if response.get("status") == "ok":
        return "OK"

    return ("Failed to write to tag", 502)


@app.route("/set_nfc_id/<int:spool>")
def set_nfc_id(spool: int) -> Union[str, Tuple[str, int]]:
    """
    The web-api to write the current nfc_id to spool's nfc_id field in Spoolman
    """
    response: Dict[str, Any] = ipc_client.send_request(
        {"command": "set_nfc_id", "spool": spool}
    )
    if response.get("status") == "ok":
        return "OK"

    return ("Failed to send nfc_id to Spoolman", 502)


@app.route("/")
def index() -> Union[str, Tuple[str, int]]:
    """
    Returns the main index page.
    """
    spools_response: Dict[str, Any] = ipc_client.send_request({"command": "get_spools"})
    state_response: Dict[str, Any] = ipc_client.send_request({"command": "get_state"})

    if spools_response.get("status") != "ok":
        error_msg = spools_response.get("message", "Unknown error")
        app.logger.error("Spoolman error: %s", error_msg)
        return (
            "Got error fetching spool data from Spoolman via backend: "
            + str(error_msg),
            502,
        )
    if state_response.get("status") != "ok":
        error_msg = state_response.get("message", "Unknown error")
        app.logger.error("Backend state error: %s", error_msg)
        return (
            "Got error fetching spool state from backend: " + str(error_msg),
            502,
        )

    spools: list = (
        spools_response.get("spools", [])
        if spools_response.get("status") == "ok"
        else []
    )
    nfc_id: Optional[str] = (
        state_response.get("nfc_id") if state_response.get("status") == "ok" else None
    )
    spool_id: Optional[int] = (
        state_response.get("spool_id") if state_response.get("status") == "ok" else None
    )

    return render_template(
        "index.html", spools=spools, nfc_id=nfc_id, spool_id=spool_id
    )


if __name__ == "__main__":
    app.logger.info("Starting web server")
    app.run(args["webserver"]["web_address"], port=args["webserver"]["web_port"])
