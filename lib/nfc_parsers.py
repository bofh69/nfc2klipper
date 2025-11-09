# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tag parsers for different data formats"""

import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple

import ndef

logger: logging.Logger = logging.getLogger(__name__)

SPOOL: str = "SPOOL"
FILAMENT: str = "FILAMENT"
NDEF_TEXT_TYPE: str = "urn:nfc:wkt:T"

# pylint: disable=too-few-public-methods


class TagParser(Protocol):
    """Protocol for tag parsers"""

    def parse(
        self, ndef_data: Any, identifier: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse tag data and return (spool_id, filament_id) or (None, None)

        Args:
            ndef_data: NDEF data structure from the tag (can be None)
            identifier: Tag identifier string

        Returns:
            Tuple of (spool_id, filament_id) as strings, or (None, None) if not found
        """


class NdefTextParser:
    """Parser for NDEF text records containing SPOOL and FILAMENT data

    >>> import ndef
    >>> parser = NdefTextParser()
    >>> record0 = ndef.TextRecord("")
    >>> record1 = ndef.TextRecord("SPOOL:23\\n")
    >>> record2 = ndef.TextRecord("FILAMENT:14\\n")
    >>> record3 = ndef.TextRecord("SPOOL:23\\nFILAMENT:14\\n")
    >>> class MockNdef:
    ...     def __init__(self, records): self.records = records
    >>> parser.parse(MockNdef([record0]), "aa:bb:cc")
    (None, None)
    >>> parser.parse(MockNdef([record3]), "aa:bb:cc")
    ('23', '14')
    >>> parser.parse(MockNdef([record1]), "aa:bb:cc")
    ('23', None)
    >>> parser.parse(MockNdef([record2]), "aa:bb:cc")
    (None, '14')
    >>> parser.parse(MockNdef([record0, record3]), "aa:bb:cc")
    ('23', '14')
    >>> parser.parse(MockNdef([record3, record0]), "aa:bb:cc")
    ('23', '14')
    >>> parser.parse(MockNdef([record1, record2]), "aa:bb:cc")
    ('23', '14')
    >>> parser.parse(MockNdef([record2, record1]), "aa:bb:cc")
    ('23', '14')
    >>> parser.parse(None, "aa:bb:cc")
    (None, None)
    """

    def _parse_records(self, records: List[Any]) -> Tuple[Optional[str], Optional[str]]:
        """Parse NDEF text records for SPOOL and FILAMENT data"""
        spool: Optional[str] = None
        filament: Optional[str] = None

        for record in records:
            if record.type == NDEF_TEXT_TYPE:
                for line in record.text.splitlines():
                    line_parts = line.split(":")
                    if len(line_parts) == 2:
                        if line_parts[0] == SPOOL:
                            spool = line_parts[1]
                        if line_parts[0] == FILAMENT:
                            filament = line_parts[1]
            else:
                logger.debug("Read other record: %s", record)

        return spool, filament

    def parse(
        self, ndef_data: Any, _identifier: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse NDEF text records for SPOOL and FILAMENT data"""
        if ndef_data is None:
            return None, None

        try:
            return self._parse_records(ndef_data.records)
        except ndef.record.DecodeError as ex:
            logger.debug("Could not parse NDEF records: %s", ex)
            return None, None


class TagIdentifierParser:
    """Parser that looks up spool/filament data from Spoolman using tag identifier"""

    def __init__(self, spoolman_client: Any) -> None:
        """Initialize with a Spoolman client instance

        Args:
            spoolman_client: Client object with get_spool_from_nfc_id method
        """
        self.spoolman_client = spoolman_client

    def parse(
        self, _ndef_data: Any, identifier: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Query Spoolman for spool/filament data using tag identifier"""
        logger.debug("Fetching data from spoolman from tags' id: %s", identifier)
        spool_data: Optional[Dict[str, Any]] = (
            self.spoolman_client.get_spool_from_nfc_id(identifier)
        )
        if spool_data:
            spool_id = spool_data.get("id")
            filament_id = None
            if "filament" in spool_data:
                filament_data = spool_data["filament"]
                if filament_data:
                    filament_id = filament_data.get("id")
            if spool_id is not None and filament_id is not None:
                return str(spool_id), str(filament_id)

        logger.debug(
            "Did not find spool data for tag id (%s) in spoolman",
            identifier,
        )
        return None, None
