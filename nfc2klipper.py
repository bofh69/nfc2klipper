#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags."""

import logging
import os
import sys
import subprocess  # nosec
import time

from lib.config import Nfc2KlipperConfig

Nfc2KlipperConfig.configure_logging()

logger = logging.getLogger(__name__)

args = Nfc2KlipperConfig.get_config()

if not args:
    # Run the backend to handle initial config setup
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(script_dir, "nfc2klipper_backend.py")
    subprocess.run([sys.executable, backend_script], check=False)  # nosec
    sys.exit(1)

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(script_dir, "nfc2klipper_backend.py")
    api_script = os.path.join(script_dir, "nfc2klipper_api.py")

    if not args["webserver"].get("disable_web_server"):
        # Start backend in a separate process
        logger.info("Starting backend service")
        with subprocess.Popen(
            [sys.executable, backend_script]
        ) as backend_process:  # nosec
            # Wait a moment for the backend to start
            time.sleep(2)

            logger.info("Starting web API service")
            try:
                with subprocess.Popen(
                    [sys.executable, api_script]
                ) as api_process:  # nosec
                    # Wait for both processes to end
                    backend_process.wait()
                    api_process.wait()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
    else:
        # Just run the backend
        subprocess.run([sys.executable, backend_script], check=True)  # nosec
