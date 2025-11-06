#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Backend service for NFC handling and communication with Moonraker/Spoolman."""

import inspect
import json
import logging
import os
import signal
import socket
import sys
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

import toml

from lib.moonraker_web_client import MoonrakerWebClient
from lib.nfc_handler import NfcHandler
from lib.spoolman_client import SpoolmanClient


# Request handler registry
_request_handlers: Dict[str, Callable[..., Dict[str, Any]]] = {}


def request_handler(command_name: str) -> Callable:
    """Decorator to register a request handler for a specific command"""

    def decorator(func: Callable[..., Dict[str, Any]]) -> Callable:
        _request_handlers[command_name] = func
        return func

    return decorator


CFG_DIR: str = "~/.config/nfc2klipper"
DEFAULT_SOCKET_PATH: str = "/home/pi/nfc2klipper/nfc2klipper.sock"

# pylint: disable=duplicate-code
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s: %(message)s"
)
logger: logging.Logger = logging.getLogger(__name__)

args: Optional[Dict[str, Any]] = None  # pylint: disable=C0103
for path in ["~/nfc2klipper.cfg", CFG_DIR + "/nfc2klipper.cfg"]:
    cfg_filename: str = os.path.expanduser(path)
    if os.path.exists(cfg_filename):
        with open(cfg_filename, "r", encoding="utf-8") as fp:
            args = toml.load(fp)
            break

if not args:
    print(
        "WARNING: The config file is missing, installing a default version.",
        file=sys.stderr,
    )
    cfg_dir: str = os.path.expanduser(CFG_DIR)
    if not os.path.exists(cfg_dir):
        print(f"Creating dir {cfg_dir}", file=sys.stderr)
        Path(cfg_dir).mkdir(parents=True, exist_ok=True)
    script_dir: str = os.path.dirname(__file__)
    from_filename: str = os.path.join(script_dir, "nfc2klipper.cfg")
    to_filename: str = os.path.join(cfg_dir, "nfc2klipper.cfg")
    shutil.copyfile(from_filename, to_filename)
    print(f"Created {to_filename}, please update it", file=sys.stderr)
    sys.exit(1)

# Get socket path from config, with fallback to default
socket_path: str = args.get("webserver", {}).get("socket_path", DEFAULT_SOCKET_PATH)
socket_path = os.path.expanduser(socket_path)

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
        MockMoonrakerWebClient(args["moonraker"]["moonraker-url"])
    )
    nfc_handler: Union[NfcHandler, "MockNfcHandler"] = MockNfcHandler(
        args["nfc"]["nfc-device"]
    )
else:
    spoolman = SpoolmanClient(args["spoolman"]["spoolman-url"])
    moonraker = MoonrakerWebClient(args["moonraker"]["moonraker-url"])
    nfc_handler = NfcHandler(args["nfc"]["nfc-device"])

last_nfc_id: Optional[str] = None  # pylint: disable=C0103
last_spool_id: Optional[str] = None  # pylint: disable=C0103


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
        moonraker.set_spool_and_filament(spool, filament)
    except Exception as ex:  # pylint: disable=W0718
        logger.error(ex)
        return

    set_spool_and_filament.old_spool = spool  # type: ignore[attr-defined]
    set_spool_and_filament.old_filament = filament  # type: ignore[attr-defined]


def should_clear_spool() -> bool:
    """Returns True if the config says the spool should be cleared"""
    assert args is not None  # nosec
    if args["moonraker"].get("clear_spool"):
        return True
    return False


def on_nfc_tag_present(
    spool: Optional[str], filament: Optional[str], identifier: str
) -> None:
    """Handles a read tag"""

    if identifier:
        global last_nfc_id  # pylint: disable=W0603
        last_nfc_id = identifier
    if spool:
        global last_spool_id  # pylint: disable=W0603
        last_spool_id = spool

    if not (spool and filament):
        logger.debug("Fetching data from spoolman from tags' id: %s", identifier)
        spool_data = spoolman.get_spool_from_nfc_id(identifier)
        if spool_data:
            spool_int = spool_data.get("id")
            filament_int = None
            if "filament" in spool_data:
                filament_int = spool_data["filament"].get("id")
        else:
            logger.info(
                "Did not find spool records in tag nor from its id (%s) in spoolman",
                identifier,
            )
            return
    else:
        # Convert string to int if needed
        spool_int = int(spool) if spool else 0
        filament_int = int(filament) if filament else 0

    if spool_int is not None and filament_int is not None:
        set_spool_and_filament(spool_int, filament_int)


def on_nfc_no_tag_present() -> None:
    """Called when no tag is present (or tag without data)"""
    if should_clear_spool():
        set_spool_and_filament(0, 0)


@request_handler("write_tag")
def handle_write_tag(spool: int, filament: int) -> Dict[str, Any]:
    """Handle write_tag command"""
    logger.info("  write spool=%s, filament=%s", spool, filament)
    if nfc_handler.write_to_tag(spool, filament):
        return {"status": "ok"}
    return {"status": "error", "message": "Failed to write to tag"}


@request_handler("set_nfc_id")
def handle_set_nfc_id(spool: int) -> Dict[str, Any]:
    """Handle set_nfc_id command"""
    global last_nfc_id  # pylint: disable=W0602,W0603
    logger.info("Set nfc_id=%s to spool=%s in Spoolman", last_nfc_id, spool)

    if last_nfc_id is None:
        return {"status": "error", "message": "No nfc_id to write"}

    if spoolman.set_nfc_id_for_spool(spool, last_nfc_id):
        return {"status": "ok"}

    return {"status": "error", "message": "Failed to send nfc_id to Spoolman"}


@request_handler("get_spools")
def handle_get_spools() -> Dict[str, Any]:
    """Handle get_spools command"""
    spools = spoolman.get_spools()
    return {"status": "ok", "spools": spools}


@request_handler("get_state")
def handle_get_state() -> Dict[str, Any]:
    """Handle get_state command"""
    return {
        "status": "ok",
        "nfc_id": last_nfc_id,
        "spool_id": last_spool_id,
    }


def handle_client_request(request_data: str) -> Dict[str, Any]:
    """Handle a request from the web API"""
    try:
        request = json.loads(request_data)
        command = request.get("command")

        # Look up the handler for this command
        if command in _request_handlers:
            handler = _request_handlers[command]
            # Extract arguments based on handler function signature
            sig = inspect.signature(handler)
            kwargs = {}
            for param_name in sig.parameters:
                if param_name in request:
                    kwargs[param_name] = request[param_name]
            return handler(**kwargs)

        return {"status": "error", "message": f"Unknown command: {command}"}

    except Exception as ex:  # pylint: disable=W0718
        logger.exception("Error handling request: %s", ex)
        return {"status": "error", "message": str(ex)}


def run_socket_server() -> None:
    """Run the Unix domain socket server"""
    # Ensure the directory for the socket exists
    socket_dir: str = os.path.dirname(socket_path)
    if socket_dir and not os.path.exists(socket_dir):
        try:
            os.makedirs(socket_dir, exist_ok=True)
            logger.info("Created socket directory: %s", socket_dir)
        except OSError as ex:
            logger.error(
                "ERROR: Failed to create directory for socket: %s\n"
                "  Directory: %s\n"
                "  Error: %s\n"
                "  Fix: Ensure the parent directory exists and you have write permissions.\n"
                "       You can also change the socket_path in the config file "
                "[webserver] section.",
                socket_path,
                socket_dir,
                ex,
            )
            sys.exit(1)

    # Remove socket file if it exists
    if os.path.exists(socket_path):
        try:
            os.unlink(socket_path)
        except OSError as ex:
            logger.error(
                "ERROR: Failed to remove existing socket file: %s\n"
                "  Socket: %s\n"
                "  Error: %s\n"
                "  Fix: Ensure you have write permissions or manually remove the file.\n"
                "       You can also change the socket_path in the config file "
                "[webserver] section.",
                socket_path,
                socket_path,
                ex,
            )
            sys.exit(1)

    try:
        server: socket.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(socket_path)
        server.listen(5)
        logger.info("Socket server listening on %s", socket_path)
    except OSError as ex:
        logger.error(
            "ERROR: Failed to create socket: %s\n"
            "  Socket: %s\n"
            "  Error: %s\n"
            "  Fix: Ensure the directory exists and you have write permissions.\n"
            "       Check if another process is using this socket path.\n"
            "       You can also change the socket_path in the config file "
            "[webserver] section.",
            socket_path,
            socket_path,
            ex,
        )
        sys.exit(1)

    while True:
        try:
            conn: socket.socket
            conn, _ = server.accept()
            data: str = conn.recv(65536).decode("utf-8")
            if data:
                response: Dict[str, Any] = handle_client_request(data)
                conn.sendall(json.dumps(response).encode("utf-8"))
            conn.close()
        except Exception as ex:  # pylint: disable=W0718
            logger.exception("Error in socket server: %s", ex)


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
    socket_thread = threading.Thread(target=run_socket_server)
    socket_thread.daemon = True
    socket_thread.start()

    logger.info("Starting nfc-handler")
    try:
        nfc_handler.run()
    except (KeyboardInterrupt, SystemExit):
        signal_handler(signal.SIGINT, None)
