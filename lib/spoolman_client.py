# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spoolman client"""

import json
import logging
from typing import Any, Dict, List, Optional
import requests

logger: logging.Logger = logging.getLogger(__name__)


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

    def find_vendor_by_name(self, name: str) -> Optional[int]:
        """Find a vendor by name

        Args:
            name: Vendor name to search for

        Returns:
            Vendor ID if found, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/vendor"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                logger.error(
                    "Failed to find vendor '%s': HTTP %d - %s",
                    name,
                    response.status_code,
                    response.text,
                )
                return None

            vendors = response.json()

            # Search for matching vendor (case-insensitive)
            for vendor in vendors:
                if vendor.get("name", "").lower() == name.lower():
                    return vendor["id"]

            return None
        except Exception as ex:  # pylint: disable=W0718
            logger.error("Exception while finding vendor '%s': %s", name, ex)
            return None

    def create_vendor(self, name: str) -> Optional[int]:
        """Create a new vendor

        Args:
            name: Vendor name

        Returns:
            Vendor ID if created successfully, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/vendor"
            data = {"name": name}
            response = requests.post(url, json=data, timeout=10)
            if response.status_code not in (200, 201):
                logger.error(
                    "Failed to create vendor '%s': HTTP %d - %s",
                    name,
                    response.status_code,
                    response.text,
                )
                return None

            vendor = response.json()
            return vendor.get("id")
        except Exception as ex:  # pylint: disable=W0718
            logger.error("Exception while creating vendor '%s': %s", name, ex)
            return None

    def find_filament_by_vendor_and_name(
        self, vendor_id: int, name: str
    ) -> Optional[int]:
        """Find a filament by vendor ID and name

        Args:
            vendor_id: Vendor ID
            name: Filament name

        Returns:
            Filament ID if found, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/filament"
            params = {"vendor_id": vendor_id}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                logger.error(
                    "Failed to find filament '%s' for vendor %d: HTTP %d - %s",
                    name,
                    vendor_id,
                    response.status_code,
                    response.text,
                )
                return None

            filaments = response.json()

            # Search for matching filament (case-insensitive)
            for filament in filaments:
                if filament.get("name", "").lower() == name.lower():
                    return filament["id"]

            return None
        except Exception as ex:  # pylint: disable=W0718
            logger.error(
                "Exception while finding filament '%s' for vendor %d: %s",
                name,
                vendor_id,
                ex,
            )
            return None

    def find_filament_by_vendor_material_and_name(
        self, vendor_id: int, material: str, name: str
    ) -> Optional[int]:
        """Find a filament by vendor ID, material, and name

        Args:
            vendor_id: Vendor ID
            material: Filament material (e.g., "PLA", "PETG-CF")
            name: Filament name

        Returns:
            Filament ID if found, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/filament"
            params = {"vendor_id": vendor_id}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                logger.error(
                    "Failed to find filament '%s' (material: %s) for vendor %d: HTTP %d - %s",
                    name,
                    material,
                    vendor_id,
                    response.status_code,
                    response.text,
                )
                return None

            filaments = response.json()

            # Search for matching filament (case-insensitive) by material AND name
            for filament in filaments:
                if (
                    filament.get("name", "").lower() == name.lower()
                    and filament.get("material", "").lower() == material.lower()
                ):
                    return filament["id"]

            return None
        except Exception as ex:  # pylint: disable=W0718
            logger.error(
                "Exception while finding filament '%s' (material: %s) for vendor %d: %s",
                name,
                material,
                vendor_id,
                ex,
            )
            return None

    def create_filament(
        self,
        data: Dict[str, Any],
    ) -> Optional[int]:
        """Create a new filament

        Args:
            data: Dictionary containing filament data fields to send to Spoolman API
                  Required: vendor_id, name, material, density, diameter, color_hex
                  Optional: weight, settings_bed_temp, settings_extruder_temp,
                           multi_color_hexes, extra, etc.

        Returns:
            Filament ID if created successfully, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/filament"
            logger.debug("Creating new filament: %s", data)
            response = requests.post(url, json=data, timeout=10)
            if response.status_code not in (200, 201):
                logger.error(
                    "Failed to create filament: HTTP %d - %s",
                    response.status_code,
                    response.text,
                )
                return None

            filament = response.json()
            return filament.get("id")
        except Exception as ex:  # pylint: disable=W0718
            logger.error("Exception while creating filament: %s", ex)
            return None

    def create_spool(
        self,
        data: Dict[str, Any],
    ) -> Optional[int]:
        """Create a new spool

        Args:
            data: Dictionary containing spool data fields to send to Spoolman API
                  Required: filament_id
                  Optional: remaining_weight, lot_nr, extra, etc.

        Returns:
            Spool ID if created successfully, None otherwise
        """
        try:
            url: str = self.url + "/api/v1/spool"
            logger.debug("Creating new spool: %s", data)
            response = requests.post(url, json=data, timeout=10)
            if response.status_code not in (200, 201):
                logger.error(
                    "Failed to create spool: HTTP %d - %s",
                    response.status_code,
                    response.text,
                )
                return None

            spool = response.json()
            return spool.get("id")
        except Exception as ex:  # pylint: disable=W0718
            logger.error("Exception while creating spool: %s", ex)
            return None
