# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spoolman client"""

import json
import requests


# pylint: disable=R0903
class SpoolmanClient:
    """Spoolman Web Client"""

    def __init__(self, url: str):
        if url.endswith("/"):
            url = url[:-1]
        self.url = url

    def get_spools(self):
        """Get the spools from spoolman"""
        url = self.url + "/api/v1/spool"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}")
        records = json.loads(response.text)
        return records
