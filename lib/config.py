#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read config file"""

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import toml


class Nfc2KlipperConfig:
    """Class to handle configuration data for the application"""

    CFG_DIR: str = "~/.config/nfc2klipper"
    DEFAULT_SOCKET_PATH: str = "~/nfc2klipper/nfc2klipper.sock"

    @classmethod
    def configure_logging(cls) -> None:
        """Configure the logging"""
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s - %(name)s: %(message)s",
        )

    @classmethod
    def get_config(cls) -> Optional[Dict[str, Any]]:
        """Get the config data, or None if missing"""
        for path in [
            "~/nfc2klipper.cfg",
            Nfc2KlipperConfig.CFG_DIR + "/nfc2klipper.cfg",
        ]:
            cfg_filename: str = os.path.expanduser(path)
            if os.path.exists(cfg_filename):
                with open(cfg_filename, "r", encoding="utf-8") as fp:
                    return toml.load(fp)
        return None

    @classmethod
    def install_config(cls) -> None:
        """Copy the default config file to the right place"""
        cfg_dir: str = os.path.expanduser(Nfc2KlipperConfig.CFG_DIR)
        if not os.path.exists(cfg_dir):
            print(f"Creating dir {cfg_dir}", file=sys.stderr)
            Path(cfg_dir).mkdir(parents=True, exist_ok=True)
        script_dir: str = os.path.dirname(__file__)
        from_filename: str = os.path.join(script_dir, "../nfc2klipper.cfg")
        to_filename: str = os.path.join(cfg_dir, "nfc2klipper.cfg")
        shutil.copyfile(from_filename, to_filename)
        print(f"Created {to_filename}, please update it", file=sys.stderr)

    @classmethod
    def get_setting_gcode(cls, config: Dict[str, Any]) -> List[str]:
        """Get spool & filament setting gcode templates from config, or default value"""

        macros_config: Optional[Dict[str, Any]] = config.get("macros")
        setting_gcode: Optional[str] = None
        if macros_config:
            setting_gcode = macros_config.get("setting_gcode")
        if not setting_gcode:
            setting_gcode = (
                "SET_ACTIVE_SPOOL ID={spool}\n" + "SET_ACTIVE_FILAMENT ID={filament}"
            )
        return [cmd.strip() for cmd in setting_gcode.split("\n") if cmd.strip()]

    @classmethod
    def get_clearing_gcode(cls, config: Dict[str, Any]) -> List[str]:
        """Get spool & filament clearing gcode templates from config, or default value"""

        macros_config: Optional[Dict[str, Any]] = config.get("macros")
        setting_gcode: Optional[str] = None
        if macros_config:
            setting_gcode = macros_config.get("clearing_gcode")
        if not setting_gcode:
            setting_gcode = "CLEAR_ACTIVE_SPOOL\n" + "SET_ACTIVE_FILAMENT ID=0"
        return [cmd.strip() for cmd in setting_gcode.split("\n") if cmd.strip()]
