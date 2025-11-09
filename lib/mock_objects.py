#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mock objects for testing nfc2klipper without hardware"""

# pylint: disable=duplicate-code

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import ndef  # pylint: disable=import-error

logger: logging.Logger = logging.getLogger(__name__)


class MockNfcHandler:
    """Mock NFC Handler for testing"""

    def __init__(self, nfc_device: str) -> None:
        logger.info("MockNfcHandler initialized with device: %s", nfc_device)
        self.status: str = ""
        self.nfc_device: str = nfc_device
        self.on_nfc_no_tag_present: Optional[Callable[[], None]] = None
        self.on_nfc_tag_present: Optional[Callable[[Any, str], None]] = None
        self.should_stop: bool = False
        self.thread: Optional[threading.Thread] = None
        self.tag_present: bool = False

    def set_no_tag_present_callback(
        self, on_nfc_no_tag_present: Callable[[], None]
    ) -> None:
        """Sets a callback that will be called when no tag is present"""
        logger.info("MockNfcHandler: set_no_tag_present_callback registered")
        self.on_nfc_no_tag_present = on_nfc_no_tag_present

    def set_tag_present_callback(
        self,
        on_nfc_tag_present: Callable[[Any, str], None],
    ) -> None:
        """Sets a callback that will be called when a tag has been read"""
        logger.info("MockNfcHandler: set_tag_present_callback registered")
        self.on_nfc_tag_present = on_nfc_tag_present

    def write_to_tag(self, spool: int, filament: int) -> bool:
        """Mock write to tag - always succeeds"""
        logger.info(
            "MockNfcHandler: write_to_tag called with spool=%s, filament=%s",
            spool,
            filament,
        )
        return True

    def run(self) -> None:
        """Run the mock NFC handler - alternates between tag present and not present"""
        logger.info("MockNfcHandler: Starting run loop")
        iteration = 0
        while not self.should_stop:
            iteration += 1
            time.sleep(2)

            if self.should_stop:
                break

            self.tag_present = not self.tag_present

            if self.tag_present:
                if self.on_nfc_tag_present:
                    # Alternate between different mock spools
                    spool_id = str(1 + (iteration % 3))
                    filament_id = str(10 + (iteration % 3))
                    nfc_id = f"aa:bb:cc:dd:{iteration % 10:02x}"
                    # Create mock NDEF object with records

                    class MockNdef:  # pylint: disable=too-few-public-methods
                        """Mock NDEF data structure"""

                        def __init__(self, records):
                            self.records = records

                    ndef_data = MockNdef(
                        [ndef.TextRecord(f"SPOOL:{spool_id}\nFILAMENT:{filament_id}\n")]
                    )
                    logger.info(
                        "MockNfcHandler: Calling on_nfc_tag_present with "
                        "spool=%s, filament=%s, nfc_id=%s",
                        spool_id,
                        filament_id,
                        nfc_id,
                    )
                    self.on_nfc_tag_present(ndef_data, nfc_id)
            else:
                if self.on_nfc_no_tag_present:
                    logger.info("MockNfcHandler: Calling on_nfc_no_tag_present")
                    self.on_nfc_no_tag_present()

        logger.info("MockNfcHandler: Run loop stopped")

    def stop(self) -> None:
        """Stop the handler"""
        logger.info("MockNfcHandler: stop() called")
        self.should_stop = True


class MockSpoolmanClient:
    """Mock Spoolman Web Client for testing"""

    def __init__(self, url: str) -> None:
        logger.info("MockSpoolmanClient initialized with url: %s", url)
        self.url: str = url
        # Mock spool data
        self.spools: List[Dict[str, Any]] = [
            {
                "id": 1,
                "filament": {
                    "id": 10,
                    "name": "PLA Red",
                    "vendor": {"name": "McGreedy"},
                },
                "extra": {"nfc_id": '"aa:bb:cc:dd:00"'},
            },
            {
                "id": 2,
                "filament": {
                    "id": 11,
                    "name": "PETG Blue",
                    "vendor": {"name": "Flaky Inc"},
                },
                "extra": {"nfc_id": '"aa:bb:cc:dd:01"'},
            },
            {
                "id": 3,
                "filament": {
                    "id": 12,
                    "name": "ABS Black",
                    "vendor": {"name": "Too Late Company"},
                },
                "extra": {},
            },
        ]

    def get_spool(self, spool_id: int) -> Dict[str, Any]:
        """Get the spool from mock data"""
        logger.info("MockSpoolmanClient: get_spool called with spool_id=%s", spool_id)
        for spool in self.spools:
            if spool["id"] == spool_id:
                return spool
        raise ValueError(f"Spool {spool_id} not found")

    def get_spools(self) -> List[Dict[str, Any]]:
        """Get the spools from mock data"""
        logger.info(
            "MockSpoolmanClient: get_spools called, returning %d spools",
            len(self.spools),
        )
        return self.spools

    def get_spool_from_nfc_id(self, nfc_id: str) -> Optional[Dict[str, Any]]:
        """Get the spool with the given nfc_id"""
        logger.info(
            "MockSpoolmanClient: get_spool_from_nfc_id called with nfc_id=%s", nfc_id
        )
        nfc_id_lower = f'"{nfc_id.lower()}"'
        for spool in self.spools:
            if "extra" in spool:
                stored_id: Optional[str] = spool["extra"].get("nfc_id")
                if stored_id and stored_id.lower() == nfc_id_lower:
                    logger.info(
                        "MockSpoolmanClient: Found spool %s for nfc_id", spool["id"]
                    )
                    return spool
        logger.info("MockSpoolmanClient: No spool found for nfc_id")
        return None

    def clear_nfc_id_for_spool(self, spool_id: int) -> None:
        """Clear the nfc_id field for the given spool"""
        logger.info(
            "MockSpoolmanClient: clear_nfc_id_for_spool called with spool_id=%s",
            spool_id,
        )
        for spool in self.spools:
            if spool["id"] == spool_id:
                if "extra" not in spool:
                    spool["extra"] = {}
                spool["extra"]["nfc_id"] = '""'
                break

    def set_nfc_id_for_spool(self, spool_id: int, nfc_id: str) -> bool:
        """Set the nfc_id field on the given spool, clear on others"""
        logger.info(
            "MockSpoolmanClient: set_nfc_id_for_spool called with spool_id=%s, nfc_id=%s",
            spool_id,
            nfc_id,
        )
        # Clear from other spools
        existing_spool = self.get_spool_from_nfc_id(nfc_id)
        if existing_spool and existing_spool["id"] != spool_id:
            self.clear_nfc_id_for_spool(existing_spool["id"])

        # Set on target spool
        for spool in self.spools:
            if spool["id"] == spool_id:
                if "extra" not in spool:
                    spool["extra"] = {}
                spool["extra"]["nfc_id"] = f'"{nfc_id.lower()}"'
                logger.info("MockSpoolmanClient: NFC ID set successfully")
                return True
        return False

    def find_vendor_by_name(self, name: str) -> Optional[int]:
        """Find a vendor by name"""
        logger.info("MockSpoolmanClient: find_vendor_by_name called with name=%s", name)
        # Mock vendors
        vendors: List[Dict[str, Any]] = [
            {"id": 1, "name": "McGreedy"},
            {"id": 2, "name": "Flaky Inc"},
            {"id": 3, "name": "Too Late Company"},
        ]
        for vendor in vendors:
            vendor_name = vendor.get("name", "")
            if isinstance(vendor_name, str) and vendor_name.lower() == name.lower():
                logger.info("MockSpoolmanClient: Found vendor %s", vendor["id"])
                vendor_id = vendor["id"]
                if isinstance(vendor_id, int):
                    return vendor_id
        logger.info("MockSpoolmanClient: Vendor not found")
        return None

    def create_vendor(self, name: str) -> Optional[int]:
        """Create a new vendor"""
        logger.info("MockSpoolmanClient: create_vendor called with name=%s", name)
        # Return a mock vendor ID
        new_id = 100
        logger.info("MockSpoolmanClient: Created vendor with id=%s", new_id)
        return new_id

    def find_filament_by_vendor_and_name(
        self, vendor_id: int, name: str
    ) -> Optional[int]:
        """Find a filament by vendor ID and name"""
        logger.info(
            "MockSpoolmanClient: find_filament_by_vendor_and_name called "
            "with vendor_id=%s, name=%s",
            vendor_id,
            name,
        )
        for spool in self.spools:
            if "filament" in spool and spool["filament"]:
                filament = spool["filament"]
                if "vendor" in filament and filament["vendor"]:
                    # vendor = filament["vendor"]  # Not used
                    if filament.get("name", "").lower() == name.lower():
                        logger.info(
                            "MockSpoolmanClient: Found filament %s", filament["id"]
                        )
                        return filament["id"]
        logger.info("MockSpoolmanClient: Filament not found")
        return None

    def create_filament(
        self,
        data: Dict[str, Any],
    ) -> Optional[int]:
        """Create a new filament"""
        logger.info(
            "MockSpoolmanClient: create_filament called with data=%s",
            data,
        )
        # Return a mock filament ID
        new_id = 200
        logger.info("MockSpoolmanClient: Created filament with id=%s", new_id)
        return new_id

    def create_spool(
        self,
        data: Dict[str, Any],
    ) -> Optional[int]:
        """Create a new spool"""
        logger.info(
            "MockSpoolmanClient: create_spool called with data=%s",
            data,
        )
        # Create and add a new spool
        new_id = len(self.spools) + 1
        filament_id = data.get("filament_id")
        new_spool = {
            "id": new_id,
            "filament": {"id": filament_id},
            "remaining_weight": data.get("remaining_weight", 0),
            "extra": data.get("extra", {}),
        }
        self.spools.append(new_spool)
        logger.info("MockSpoolmanClient: Created spool with id=%s", new_id)
        return new_id


class MockMoonrakerWebClient:  # pylint: disable=R0903
    """Mock Moonraker Web Client for testing"""

    def __init__(
        self,
        url: str,
        setting_gcode_template: List[str],
        clearing_gcode_template: List[str],
    ) -> None:
        logger.info("MockMoonrakerWebClient initialized with url: %s", url)
        self.url: str = url
        self.setting_gcode_template: List[str] = setting_gcode_template
        self.clearing_gcode_template: List[str] = clearing_gcode_template

    def set_spool_and_filament(self, spool: int, filament: int) -> None:
        """Mock calls to moonraker with the current spool & filament"""
        # Format each command template with spool and filament values
        formatted_commands: List[str] = [
            template.format(spool=spool, filament=filament)
            for template in self.setting_gcode_template
        ]
        logger.info(
            "MockMoonrakerWebClient: set_spool_and_filament called with spool=%s, filament=%s",
            spool,
            filament,
        )
        logger.info(
            "MockMoonrakerWebClient: Would execute commands: %s", formatted_commands
        )

    def clear_spool_and_filament(self) -> None:
        """Mock calls to moonraker with the current spool & filament"""

        logger.info("MockMoonrakerWebClient: clear_spool_and_filament called")
        logger.info(
            "MockMoonrakerWebClient: Would execute commands: %s",
            self.clearing_gcode_template,
        )
