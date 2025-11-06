#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags."""

import logging
import os
import signal
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

    backend_process = None
    api_process = None

    def cleanup_processes(signum, frame):  # pylint: disable=W0613
        """Clean up subprocesses on signal"""
        logger.info("Received signal %s, shutting down...", signum)
        if api_process:
            logger.info("Terminating API process")
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("API process did not terminate, killing it")
                api_process.kill()
        if backend_process:
            logger.info("Terminating backend process")
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Backend process did not terminate, killing it")
                backend_process.kill()
        sys.exit(0)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)

    if not args["webserver"].get("disable_web_server"):
        # Start backend in a separate process
        logger.info("Starting backend service")
        backend_process = subprocess.Popen(  # pylint: disable=R1732
            [sys.executable, backend_script]
        )  # nosec

        # Wait a moment for the backend to start
        time.sleep(2)

        logger.info("Starting web API service")
        try:
            api_process = subprocess.Popen(  # pylint: disable=R1732
                [sys.executable, api_script]
            )  # nosec

            # Wait for both processes to end
            backend_process.wait()
            api_process.wait()
        except KeyboardInterrupt:
            cleanup_processes(signal.SIGINT, None)
    else:
        # Just run the backend
        subprocess.run([sys.executable, backend_script], check=True)  # nosec
