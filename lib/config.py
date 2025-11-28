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

import toml  # pylint: disable=import-error


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
    def get_config(cls, config_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the config data, or None if missing"""
        search_paths: List[str] = []

        # If config_dir is specified, only search there
        if config_dir:
            search_paths.append(os.path.join(config_dir, "nfc2klipper.cfg"))
        else:
            # Search in default locations
            search_paths.extend(
                [
                    "~/nfc2klipper.cfg",
                    Nfc2KlipperConfig.CFG_DIR + "/nfc2klipper.cfg",
                ]
            )

        for path in search_paths:
            cfg_filename: str = os.path.expanduser(path)
            if os.path.exists(cfg_filename):
                with open(cfg_filename, "r", encoding="utf-8") as fp:
                    return toml.load(fp)
        return None

    @classmethod
    def install_config(cls, config_dir: Optional[str] = None) -> None:
        """Copy the default config file to the right place"""
        cfg_dir: str = os.path.expanduser(
            config_dir if config_dir else Nfc2KlipperConfig.CFG_DIR
        )
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

    @classmethod
    def get_opentag3d_filament_name_template(cls, config: Dict[str, Any]) -> str:
        """Get OpenTag3D filament name template from config, or default value"""

        opentag3d_config: Optional[Dict[str, Any]] = config.get("opentag3d")
        template: Optional[str] = None
        if opentag3d_config:
            template = opentag3d_config.get("filament_name_template")
        if not template:
            # Default template: just the color name
            template = "{color_name}"
        return template

    @classmethod
    def get_opentag3d_filament_field_mapping(
        cls, config: Dict[str, Any]
    ) -> Dict[str, str]:
        """Get OpenTag3D to Spoolman filament field mapping from config"""

        opentag3d_config: Optional[Dict[str, Any]] = config.get("opentag3d")
        if opentag3d_config:
            mapping = opentag3d_config.get("filament_field_mapping", {})
            if mapping:
                return mapping

        # Default mapping
        return {
            "weight": "target_weight",
            "settings_bed_temp": "bed_temp",
            "settings_extruder_temp": "print_temp",
        }

    @classmethod
    def get_opentag3d_spool_field_mapping(
        cls, config: Dict[str, Any]
    ) -> Dict[str, str]:
        """Get OpenTag3D to Spoolman spool field mapping from config"""

        opentag3d_config: Optional[Dict[str, Any]] = config.get("opentag3d")
        if opentag3d_config:
            mapping = opentag3d_config.get("spool_field_mapping", {})
            if mapping:
                return mapping

        # Default mapping
        return {
            "remaining_weight": "measured_filament_weight",
            "lot_nr": "serial",
        }
