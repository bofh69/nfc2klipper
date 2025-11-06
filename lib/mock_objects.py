#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mock objects for testing nfc2klipper without hardware"""

# pylint: disable=duplicate-code

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger: logging.Logger = logging.getLogger(__name__)


class MockNfcHandler:
    """Mock NFC Handler for testing"""

    def __init__(self, nfc_device: str) -> None:
        logger.info("MockNfcHandler initialized with device: %s", nfc_device)
        self.status: str = ""
        self.nfc_device: str = nfc_device
        self.on_nfc_no_tag_present: Optional[Callable[[], None]] = None
        self.on_nfc_tag_present: Optional[
            Callable[[Optional[str], Optional[str], str], None]
        ] = None
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
        on_nfc_tag_present: Callable[[Optional[str], Optional[str], str], None],
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
                    logger.info(
                        "MockNfcHandler: Calling on_nfc_tag_present with "
                        "spool=%s, filament=%s, nfc_id=%s",
                        spool_id,
                        filament_id,
                        nfc_id,
                    )
                    self.on_nfc_tag_present(spool_id, filament_id, nfc_id)
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


class MockMoonrakerWebClient:  # pylint: disable=R0903
    """Mock Moonraker Web Client for testing"""

    def __init__(self, url: str) -> None:
        logger.info("MockMoonrakerWebClient initialized with url: %s", url)
        self.url: str = url

    def set_spool_and_filament(self, spool: int, filament: int) -> None:
        """Mock calls to moonraker with the current spool & filament"""
        logger.info(
            "MockMoonrakerWebClient: set_spool_and_filament called with spool=%s, filament=%s",
            spool,
            filament,
        )
