# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
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

    def create_vendor(self, name: str) -> Dict[str, Any]:
        """Create a vendor in Spoolman"""
        url: str = self.url + "/api/v1/vendor"
        response = requests.post(url, timeout=10, json={"name": name})
        if response.status_code not in (200, 201):
            raise ValueError(f"Request to spoolman failed: {response}: {response.text}")
        return response.json()

    def get_vendor_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get vendor by name"""
        url: str = self.url + "/api/v1/vendor"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Request to spoolman failed: {response}")
        vendors: List[Dict[str, Any]] = response.json()
        for vendor in vendors:
            if vendor.get("name", "").lower() == name.lower():
                return vendor
        return None

    def get_or_create_vendor(self, name: str) -> Dict[str, Any]:
        """Get or create a vendor by name"""
        vendor = self.get_vendor_by_name(name)
        if vendor:
            return vendor
        return self.create_vendor(name)

    def find_filament_by_vendor_material_and_name(
        self, vendor_id: int, material: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a filament by vendor ID, material, and name

        Args:
            vendor_id: Vendor ID
            material: Material type (e.g., PLA, PETG)
            name: Filament name

        Returns:
            Filament dict if found, None otherwise
        """
        url: str = self.url + "/api/v1/filament"
        params = {"vendor_id": vendor_id}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        filaments: List[Dict[str, Any]] = response.json()
        for filament in filaments:
            if (
                filament.get("name", "").lower() == name.lower()
                and filament.get("material", "").lower() == material.lower()
            ):
                return filament
        return None

    def get_or_create_filament(
        self, vendor_id: int, material: str, name: str, filament_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get existing filament or create a new one

        Args:
            vendor_id: Vendor ID
            material: Material type
            name: Filament name
            filament_data: Full filament data for creation if needed

        Returns:
            Filament dict with id
        """
        # Try to find existing filament
        existing = self.find_filament_by_vendor_material_and_name(
            vendor_id, material, name
        )
        if existing:
            return existing
        # Create new filament if not found
        return self.create_filament(filament_data)

    def create_filament(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a filament in Spoolman with the given data"""
        url: str = self.url + "/api/v1/filament"
        response = requests.post(url, timeout=10, json=data)
        if response.status_code not in (200, 201):
            raise ValueError(f"Request to spoolman failed: {response}: {response.text}")
        return response.json()

    def create_spool(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a spool in Spoolman with the given data"""
        url: str = self.url + "/api/v1/spool"
        response = requests.post(url, timeout=10, json=data)
        if response.status_code not in (200, 201):
            raise ValueError(f"Request to spoolman failed: {response}: {response.text}")
        return response.json()
