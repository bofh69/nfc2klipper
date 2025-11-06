# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spoolman client"""

import json
from typing import Any, Dict, List, Optional
import requests


# pylint: disable=R0903
class SpoolmanClient:
    """Spoolman Web Client"""

    def __init__(self, url: str) -> None:
        if url.endswith("/"):
            url = url[:-1]
        self.url: str = url

    def get_spool(self, spool_id: int) -> Dict[str, Any]:
        """Get the spool from Spoolman"""
        url: str = self.url + f"/api/v1/spool/{spool_id}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}")
        return response.json()

    def get_spools(self) -> List[Dict[str, Any]]:
        """Get the spools from spoolman"""
        url: str = self.url + "/api/v1/spool"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}")
        records: List[Dict[str, Any]] = json.loads(response.text)
        return records

    def get_spool_from_nfc_id(self, nfc_id: str) -> Optional[Dict[str, Any]]:
        """Get the spool with the given nfc_id"""
        nfc_id = f'"{nfc_id.lower()}"'
        spools: List[Dict[str, Any]] = self.get_spools()
        for spool in spools:
            if "extra" in spool:
                stored_id: Optional[str] = spool["extra"].get("nfc_id")
                if stored_id:
                    stored_id = stored_id.lower()
                if stored_id == nfc_id:
                    return spool

        return None

    def clear_nfc_id_for_spool(self, spool_id: int) -> None:
        """Clear the nfc_id field for the given spool"""
        spool: Dict[str, Any] = self.get_spool(spool_id)

        extra: Optional[Dict[str, Any]] = spool.get("extra")
        if not extra:
            extra = {}
        extra["nfc_id"] = '""'

        url: str = self.url + f"/api/v1/spool/{spool_id}"
        response = requests.patch(url, timeout=10, json={"extra": extra})
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}: {response.text}")

    def set_nfc_id_for_spool(self, spool_id: int, nfc_id: str) -> bool:
        """Set the nfc_id field on the given spool, clear on others"""
        spool: Optional[Dict[str, Any]] = self.get_spool_from_nfc_id(nfc_id)

        if spool and spool["id"] == spool_id:
            # Already set on the right spool
            return True

        if spool:
            self.clear_nfc_id_for_spool(spool["id"])

        nfc_id = f'"{nfc_id.lower()}"'
        spool_dict: Dict[str, Any] = self.get_spool(spool_id)

        extra: Optional[Dict[str, Any]] = spool_dict.get("extra")
        if not extra:
            extra = {}
        extra["nfc_id"] = nfc_id

        url: str = self.url + f"/api/v1/spool/{spool_id}"
        response = requests.patch(url, timeout=10, json={"extra": extra})
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}: {response.text}")

        return True
