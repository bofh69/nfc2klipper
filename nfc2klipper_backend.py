#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "toml==0.10.2",
#   "nfcpy==1.0.4",
#   "requests==2.32.4",
# ]
# ///

"""Backend service for NFC handling and communication with Moonraker/Spoolman."""

import argparse
import logging
import os
import signal
import sys
import threading
from typing import Any, Dict, List, Optional, Union

from lib.config import Nfc2KlipperConfig
from lib.ipc import IPCServer
from lib.moonraker_web_client import MoonrakerWebClient
from lib.nfc_handler import create_nfc_handler
from lib.nfc_interface import NfcInterface
from lib.nfc_parsers import NdefTextParser, TagIdentifierParser
from lib.opentag3d_parser import OpenTag3DParser
from lib.openprinttag_parser import OpenPrintTagParser
from lib.spoolman_client import SpoolmanClient

Nfc2KlipperConfig.configure_logging()
logger: logging.Logger = logging.getLogger(__name__)

# Parse command line arguments
# pylint: disable=duplicate-code
parser = argparse.ArgumentParser(
    description="Backend service for NFC handling and communication with Moonraker/Spoolman."
)
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
        "WARNING: The config file is missing, installing a default version.",
        file=sys.stderr,
    )
    Nfc2KlipperConfig.install_config(parsed_args.config_dir)
    sys.exit(1)

args: Dict[str, Any] = args

# Get socket path from config, with fallback to default
socket_path: str = args.get("webserver", {}).get(
    "socket_path", Nfc2KlipperConfig.DEFAULT_SOCKET_PATH
)
socket_path = os.path.expanduser(socket_path)

# Get command templates from config
setting_gcode_template: List[str] = Nfc2KlipperConfig.get_setting_gcode(args)
clearing_gcode_template: List[str] = Nfc2KlipperConfig.get_clearing_gcode(args)

logger.info("Using setting_gcode: %s", setting_gcode_template)
logger.info("Using clearing_gcode: %s", clearing_gcode_template)

# Check if we should use mock objects
USE_MOCK_OBJECTS: bool = os.environ.get("NFC2KLIPPER_USE_MOCKS", "").lower() in (
    "1",
    "true",
    "yes",
)

if USE_MOCK_OBJECTS:
    logger.info("Using mock objects for testing")
    from lib.mock_objects import (
        MockNfcHandler,
        MockSpoolmanClient,
        MockMoonrakerWebClient,
    )

    spoolman: Union[SpoolmanClient, "MockSpoolmanClient"] = MockSpoolmanClient(
        args["spoolman"]["spoolman-url"]
    )
    moonraker: Union[MoonrakerWebClient, "MockMoonrakerWebClient"] = (
        MockMoonrakerWebClient(
            args["moonraker"]["moonraker-url"],
            setting_gcode_template,
            clearing_gcode_template,
        )
    )
    nfc_handler: NfcInterface = MockNfcHandler(args["nfc"]["nfc-device"])
else:
    spoolman = SpoolmanClient(args["spoolman"]["spoolman-url"])
    moonraker = MoonrakerWebClient(
        args["moonraker"]["moonraker-url"],
        setting_gcode_template,
        clearing_gcode_template,
    )
    nfc_handler = create_nfc_handler(
        args["nfc"]["nfc-device"],
        args["nfc"].get("nfc-reader", "nfcpy"),
    )

last_nfc_id: Optional[str] = None  # pylint: disable=C0103
last_spool_id: Optional[str] = None  # pylint: disable=C0103

# Create IPC server instance
ipc_server: IPCServer = IPCServer(socket_path)

# Get OpenTag3D filament name template
opentag3d_filament_template: str = (
    Nfc2KlipperConfig.get_opentag3d_filament_name_template(args)
)
logger.info("Using OpenTag3D filament name template: %s", opentag3d_filament_template)

# Get OpenTag3D field mappings
opentag3d_filament_mapping: Dict[str, str] = (
    Nfc2KlipperConfig.get_opentag3d_filament_field_mapping(args)
)
opentag3d_spool_mapping: Dict[str, str] = (
    Nfc2KlipperConfig.get_opentag3d_spool_field_mapping(args)
)
logger.info("OpenTag3D filament field mapping: %s", opentag3d_filament_mapping)
logger.info("OpenTag3D spool field mapping: %s", opentag3d_spool_mapping)

openprinttag_filament_template: str = (
    Nfc2KlipperConfig.get_openprinttag_filament_name_template(args)
)
logger.info(
    "Using OpenPrintTag filament name template: %s", openprinttag_filament_template
)

# Get OpenPrintTag field mappings
openprinttag_filament_mapping: Dict[str, str] = (
    Nfc2KlipperConfig.get_openprinttag_filament_field_mapping(args)
)
openprinttag_spool_mapping: Dict[str, str] = (
    Nfc2KlipperConfig.get_openprinttag_spool_field_mapping(args)
)
logger.info("OpenPrintTag filament field mapping: %s", openprinttag_filament_mapping)
logger.info("OpenPrintTag spool field mapping: %s", openprinttag_spool_mapping)

# Create parsers for different tag formats
# List of parsers to try in order:
# 1. NDEF text parser for simple SPOOL:X FILAMENT:Y format
# 2. Tag ID lookup in Spoolman's nfc_id extra field
# 3. OpenTag3D parser - only called if tag not found via nfc_id
parsers: List[Any] = [
    TagIdentifierParser(spoolman),
    NdefTextParser(),
    OpenPrintTagParser(
        spoolman,
        openprinttag_filament_template,
        openprinttag_filament_mapping,
        openprinttag_spool_mapping,
    ),
    OpenTag3DParser(
        spoolman,
        opentag3d_filament_template,
        opentag3d_filament_mapping,
        opentag3d_spool_mapping,
    ),
]


def should_always_send() -> bool:
    """Should SET_ACTIVE_* macros always be called when tag is read,
    or only when different?"""
    assert args is not None  # nosec
    always_send: Optional[bool] = args["moonraker"].get("always-send")

    if always_send is None:
        return False

    return always_send


def set_spool_and_filament(spool: int, filament: int) -> None:
    """Calls moonraker with the current spool & filament"""

    if "old_spool" not in set_spool_and_filament.__dict__:  # type: ignore[attr-defined]
        set_spool_and_filament.old_spool = None  # type: ignore[attr-defined]
        set_spool_and_filament.old_filament = None  # type: ignore[attr-defined]

    if not should_always_send() and (
        set_spool_and_filament.old_spool == spool  # type: ignore[attr-defined]
        and set_spool_and_filament.old_filament == filament  # type: ignore[attr-defined]
    ):
        logger.info("Read same spool & filament")
        return

    logger.info("Sending spool #%s, filament #%s to klipper", spool, filament)

    # In case the post fails, we might not know if the server has received
    # it or not, so set them to None:
    set_spool_and_filament.old_spool = None  # type: ignore[attr-defined]
    set_spool_and_filament.old_filament = None  # type: ignore[attr-defined]

    try:
        if spool and filament:
            moonraker.set_spool_and_filament(spool, filament)
        else:
            moonraker.clear_spool_and_filament()
    except Exception as ex:  # pylint: disable=W0718
        logger.error(ex)
        return

    set_spool_and_filament.old_spool = spool  # type: ignore[attr-defined]
    set_spool_and_filament.old_filament = filament  # type: ignore[attr-defined]


def should_clear_spool() -> bool:
    """Returns True if the config says the spool should be cleared"""
    assert args is not None  # nosec
    if args["moonraker"].get("clear-spool"):
        return True
    return False


def on_nfc_tag_present(ndef_data: Any, identifier: str) -> None:
    """Handles a read tag"""

    if identifier:
        global last_nfc_id  # pylint: disable=W0603
        last_nfc_id = identifier

    # Try each parser in order until one returns valid spool and filament data
    spool: Optional[str] = None
    filament: Optional[str] = None

    for tag_parser in parsers:
        spool_and_filament = tag_parser.parse(ndef_data, identifier)
        if spool_and_filament:
            spool, filament = spool_and_filament
            if spool and filament:
                # Found valid data, stop trying other parsers
                break

    if spool:
        global last_spool_id  # pylint: disable=W0603
        last_spool_id = spool

    if spool and filament:
        # Convert string to int
        spool_int = int(spool)
        filament_int = int(filament)
        set_spool_and_filament(spool_int, filament_int)
    else:
        logger.info(
            "Did not find spool and filament data in tag (%s)",
            identifier,
        )


def on_nfc_no_tag_present() -> None:
    """Called when no tag is present (or tag without data)"""
    if should_clear_spool():

        set_spool_and_filament(0, 0)


@ipc_server.register_handler("write_tag")
def handle_write_tag(spool: int, filament: int) -> Dict[str, Any]:
    """Handle write_tag command"""
    logger.info("  write spool=%s, filament=%s", spool, filament)
    if nfc_handler.write_to_tag(spool, filament):
        return {"status": "ok"}
    return {"status": "error", "message": "Failed to write to tag"}


@ipc_server.register_handler("set_nfc_id")
def handle_set_nfc_id(spool: int) -> Dict[str, Any]:
    """Handle set_nfc_id command"""
    global last_nfc_id  # pylint: disable=W0602,W0603
    logger.info("Set nfc_id=%s to spool=%s in Spoolman", last_nfc_id, spool)

    if last_nfc_id is None:
        return {"status": "error", "message": "No nfc_id to write"}

    if spoolman.set_nfc_id_for_spool(spool, last_nfc_id):
        return {"status": "ok"}

    return {"status": "error", "message": "Failed to send nfc_id to Spoolman"}


@ipc_server.register_handler("get_spools")
def handle_get_spools() -> Dict[str, Any]:
    """Handle get_spools command"""
    spools = spoolman.get_spools()
    return {"status": "ok", "spools": spools}


@ipc_server.register_handler("get_state")
def handle_get_state() -> Dict[str, Any]:
    """Handle get_state command"""
    return {
        "status": "ok",
        "nfc_id": last_nfc_id,
        "spool_id": last_spool_id,
    }


if __name__ == "__main__":

    def signal_handler(signum, _frame):
        """Handle termination signals"""
        logger.info("Received signal %s, shutting down...", signum)
        nfc_handler.stop()
        # Clean up socket file
        if os.path.exists(socket_path):
            try:
                os.unlink(socket_path)
            except OSError:
                pass
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if should_clear_spool():
        # Start by unsetting current spool & filament:
        set_spool_and_filament(0, 0)

    nfc_handler.set_no_tag_present_callback(on_nfc_no_tag_present)
    nfc_handler.set_tag_present_callback(on_nfc_tag_present)

    logger.info("Starting socket server")
    socket_thread = threading.Thread(target=ipc_server.start)
    socket_thread.daemon = True
    socket_thread.start()

    logger.info("Starting nfc-handler")
    try:
        nfc_handler.run()
    except (KeyboardInterrupt, SystemExit):
        signal_handler(signal.SIGINT, None)
