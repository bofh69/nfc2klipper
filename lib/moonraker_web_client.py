# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Moonraker Web Client"""

from typing import Dict, List

import requests


# pylint: disable=R0903
class MoonrakerWebClient:
    """Moonraker Web Client"""

    def __init__(
        self,
        url: str,
        setting_gcode_template: List[str],
        clearing_gcode_template: List[str],
    ) -> None:
        self.url: str = url
        self.setting_gcode_template: List[str] = setting_gcode_template
        self.clearing_gcode_template: List[str] = clearing_gcode_template

    def set_spool_and_filament(self, spool: int, filament: int) -> None:
        """Calls moonraker with the current spool & filament"""

        # Format each command template with spool and filament values
        formatted_commands: List[str] = [
            template.format(spool=spool, filament=filament)
            for template in self.setting_gcode_template
        ]

        commands: Dict[str, List[str]] = {"commands": formatted_commands}

        response = requests.post(
            self.url + "/api/printer/command", timeout=10, json=commands
        )
        if response.status_code != 200:
            raise ValueError(f"Request to moonraker failed: {response}")

    def clear_spool_and_filament(self) -> None:
        """Calls moonraker to clear the current spool & filament"""

        commands: Dict[str, List[str]] = {"commands": self.clearing_gcode_template}

        response = requests.post(
            self.url + "/api/printer/command", timeout=10, json=commands
        )
        if response.status_code != 200:
            raise ValueError(f"Request to moonraker failed: {response}")
