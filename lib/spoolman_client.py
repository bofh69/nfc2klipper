# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spoolman client"""

import json
from typing import Any, Optional
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

    def get_spool_from_nfc_id(self, nfc_id: str) -> Optional[Any]:
        """Get the spool with the given nfc_id"""
        nfc_id = f'"{nfc_id}"'
        spools = self.get_spools()
        for spool in spools:
            if "extra" in spool:
                stored_id = spool["extra"].get("nfc_id")
                if stored_id == nfc_id:
                    return spool

        return None
