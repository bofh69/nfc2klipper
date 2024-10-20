# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Moonraker Web Client"""

import requests


# pylint: disable=R0903
class MoonrakerWebClient:
    """Moonraker Web Client"""

    def __init__(self, url: str):
        self.url = url

    def set_spool_and_filament(self, spool: int, filament: int):
        """Calls moonraker with the current spool & filament"""

        commands = {
            "commands": [
                f"SET_ACTIVE_SPOOL ID={spool}",
                f"SET_ACTIVE_FILAMENT ID={filament}",
            ]
        }

        response = requests.post(
            self.url + "/api/printer/command", timeout=10, json=commands
        )
        if response.status_code != 200:
            raise ValueError(f"Request to moonraker failed: {response}")
