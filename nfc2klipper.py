#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags."""

import logging
import os
import sys
import subprocess
import time

import toml

CFG_DIR = "~/.config/nfc2klipper"

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s %(levelname)s - %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

args = None  # pylint: disable=C0103
for path in ["~/nfc2klipper.cfg", CFG_DIR + "/nfc2klipper.cfg"]:
    cfg_filename = os.path.expanduser(path)
    if os.path.exists(cfg_filename):
        with open(cfg_filename, "r", encoding="utf-8") as fp:
            args = toml.load(fp)
            break

if not args:
    # Run the backend to handle initial config setup
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(script_dir, "nfc2klipper_backend.py")
    subprocess.run([sys.executable, backend_script], check=False)
    sys.exit(1)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(script_dir, "nfc2klipper_backend.py")
    api_script = os.path.join(script_dir, "nfc2klipper_api.py")

    if not args["webserver"].get("disable_web_server"):
        # Start backend in a separate process
        logger.info("Starting backend service")
        backend_process = subprocess.Popen([sys.executable, backend_script])

        # Wait a moment for the backend to start
        time.sleep(2)

        # Start web API
        logger.info("Starting web API service")
        api_process = None
        try:
            api_process = subprocess.Popen([sys.executable, api_script])
            # Wait for both processes
            backend_process.wait()
            api_process.wait()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            if api_process:
                api_process.terminate()
            backend_process.terminate()
    else:
        # Just run the backend
        subprocess.run([sys.executable, backend_script], check=True)
