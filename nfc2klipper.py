#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Program to set current filament & spool in klipper, and write to tags."""

import argparse
import logging
import os
import signal
import sys
import subprocess  # nosec
import time
from typing import Any, Dict, Optional

from lib.config import Nfc2KlipperConfig

Nfc2KlipperConfig.configure_logging()

logger: logging.Logger = logging.getLogger(__name__)

# Parse command line arguments
# pylint: disable=duplicate-code
parser = argparse.ArgumentParser(
    description="Program to set current filament & spool in klipper, and write to tags."
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
    # Run the backend to handle initial config setup
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    backend_script: str = os.path.join(script_dir, "nfc2klipper_backend.py")
    try:
        cmd = [sys.executable, backend_script]
        if parsed_args.config_dir:
            cmd.extend(["-c", parsed_args.config_dir])
        subprocess.run(cmd, check=True)  # nosec
    except subprocess.CalledProcessError:
        pass  # Backend already logged the error
    sys.exit(1)

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(script_dir, "nfc2klipper_backend.py")
    api_script: str = os.path.join(script_dir, "nfc2klipper_api.py")

    backend_process: Optional[subprocess.Popen] = None
    api_process: Optional[subprocess.Popen] = None

    def cleanup_processes(signum: int, _frame: Any) -> None:
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
        backend_cmd = [sys.executable, backend_script]
        if parsed_args.config_dir:
            backend_cmd.extend(["-c", parsed_args.config_dir])
        # pylint: disable=consider-using-with
        backend_process = subprocess.Popen(backend_cmd)  # nosec

        # Wait a moment for the backend to start
        time.sleep(2)

        logger.info("Starting web API service")
        try:
            api_cmd = [sys.executable, api_script]
            if parsed_args.config_dir:
                api_cmd.extend(["-c", parsed_args.config_dir])
            # pylint: disable=consider-using-with
            api_process = subprocess.Popen(api_cmd)  # nosec

            # Wait for both processes to end
            backend_process.wait()
            api_process.wait()
        except KeyboardInterrupt:
            cleanup_processes(signal.SIGINT, None)
    else:
        # Just run the backend
        cmd = [sys.executable, backend_script]
        if parsed_args.config_dir:
            cmd.extend(["-c", parsed_args.config_dir])
        subprocess.run(cmd, check=True)  # nosec
