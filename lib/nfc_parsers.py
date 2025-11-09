# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tag parsers for different data formats"""

import logging
import re
from typing import Any, Dict, List, Optional, Protocol, Tuple

import ndef  # pylint: disable=import-error

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


class OpenTag3DParser:
    """Parser for OpenTag3D format tags

    Parses tags following the OpenTag3D specification from https://opentag3d.info/spec
    Extracts manufacturer, material, color, and other filament data, then creates
    or matches entries in Spoolman.
    """

    def __init__(
        self,
        spoolman_client: Any,
        filament_name_template: str,
        filament_field_mapping: Dict[str, str],
        spool_field_mapping: Dict[str, str],
    ) -> None:
        """Initialize with a Spoolman client instance

        Args:
            spoolman_client: Client object with methods to interact with Spoolman API
            filament_name_template: Template string for generating filament names from tag data
            filament_field_mapping: Mapping from Spoolman filament fields to OpenTag3D fields
            spool_field_mapping: Mapping from Spoolman spool fields to OpenTag3D fields
        """
        self.spoolman_client = spoolman_client
        self.filament_name_template = filament_name_template
        self.filament_field_mapping = filament_field_mapping
        self.spool_field_mapping = spool_field_mapping

    def _parse_rgba_to_hex(self, octets: bytes, offset: int) -> Optional[str]:
        """Parse RGBA color at given offset and return hex string if not transparent black

        Args:
            octets: Raw bytes from the NFC tag
            offset: Byte offset to start reading RGBA (4 bytes)

        Returns:
            Hex color string (e.g., "FF0000FF") or None if transparent black
        """
        if len(octets) < offset + 4:
            return None

        r = octets[offset]
        g = octets[offset + 1]
        b = octets[offset + 2]
        a = octets[offset + 3]

        # Only return color if not transparent black (indicates no color)
        if r == 0 and g == 0 and b == 0 and a == 0:
            return None

        return f"{r:02x}{g:02x}{b:02x}{a:02x}"

    def _apply_field_mapping(
        self,
        tag_data: Dict[str, Any],
        field_mapping: Dict[str, str],
        base_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply field mapping from OpenTag3D data to Spoolman fields

        Args:
            tag_data: Parsed OpenTag3D tag data
            field_mapping: Mapping from Spoolman fields to OpenTag3D fields
            base_data: Optional base dictionary to start with

        Returns:
            Dictionary with mapped fields ready for Spoolman API
        """
        result = base_data.copy() if base_data else {}

        for spoolman_field, ot3d_field in field_mapping.items():
            if ot3d_field in tag_data:
                value = tag_data[ot3d_field]
                # Handle nested fields (e.g., "extra.custom_field")
                if "." in spoolman_field:
                    parts = spoolman_field.split(".", 1)
                    parent_key = parts[0]
                    child_key = parts[1]
                    if parent_key not in result:
                        result[parent_key] = {}
                    result[parent_key][child_key] = value
                else:
                    result[spoolman_field] = value

        return result

    def _generate_filament_name(self, tag_data: Dict[str, Any]) -> str:
        """Generate filament name from template using tag data

        Args:
            tag_data: Parsed OpenTag3D tag data

        Returns:
            Formatted filament name
        """
        # Use string formatting with the template
        try:
            # Simple approach: format with all fields, then clean up
            name = self.filament_name_template.format(**tag_data)
            # Clean up extra spaces
            name = " ".join(name.split())
            # Clean up trailing/leading dashes and spaces around dashes
            # Remove trailing dash (with optional spaces)
            name = re.sub(r"\s*-\s*$", "", name)
            # Remove leading dash (with optional spaces)
            name = re.sub(r"^\s*-\s*", "", name)
            # Clean up double spaces again after dash removal
            name = " ".join(name.split())
            return name
        except (KeyError, ValueError) as ex:
            logger.warning("Template formatting error: %s, using fallback", ex)
            # Fallback to simple material_name
            return tag_data.get("material_name", "Unknown")

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    def _parse_opentag3d_data(self, octets: bytes) -> Optional[Dict[str, Any]]:
        """Parse OpenTag3D format data from tag octets

        Args:
            octets: Raw bytes from the NFC tag

        Returns:
            Dictionary with parsed data, or None if not a valid OpenTag3D tag
        """
        # OpenTag3D data starts at offset 0x10 (16 bytes)
        # Check if we have enough data
        if len(octets) < 0x62:  # Minimum size for core fields
            return None

        # Check tag format "OT" at offset 0x10
        tag_format = octets[0x10:0x12].decode("ascii", errors="ignore")
        if tag_format != "OT":
            return None

        logger.debug("Found OpenTag3D format tag")

        # Parse tag version (2 bytes, big endian)
        tag_version = int.from_bytes(octets[0x12:0x14], byteorder="big")

        # Parse manufacturer (16 bytes UTF-8)
        manufacturer = octets[0x14:0x24].decode("utf-8", errors="ignore").rstrip("\x00")

        # Parse base material (5 bytes UTF-8)
        material_base = (
            octets[0x24:0x29].decode("utf-8", errors="ignore").rstrip("\x00")
        )

        # Parse material modifiers (5 bytes UTF-8)
        material_mod = octets[0x29:0x2E].decode("utf-8", errors="ignore").rstrip("\x00")

        # Parse color name (32 bytes UTF-8)
        color_name = octets[0x2E:0x4E].decode("utf-8", errors="ignore").rstrip("\x00")

        # Parse color 1 (4 bytes RGBA)
        color_1_hex = self._parse_rgba_to_hex(octets, 0x4E)

        # Parse target diameter (2 bytes, µm)
        target_diameter = int.from_bytes(octets[0x5A:0x5C], byteorder="big")
        diameter_mm = target_diameter / 1000.0

        # Parse target weight (2 bytes, grams)
        target_weight = int.from_bytes(octets[0x5C:0x5E], byteorder="big")

        # Parse print temperature (1 byte, divided by 5)
        print_temp_raw = octets[0x5E]
        print_temp = print_temp_raw * 5

        # Parse bed temperature (1 byte, divided by 5)
        bed_temp_raw = octets[0x5F]
        bed_temp = bed_temp_raw * 5

        # Parse density (2 bytes, µg/cm³)
        density_raw = int.from_bytes(octets[0x60:0x62], byteorder="big")
        density = density_raw / 1000.0

        # Build material name
        material_name = material_base
        if material_mod:
            material_name = f"{material_base}-{material_mod}"

        result = {
            "tag_version": tag_version,
            "manufacturer": manufacturer,
            "material_name": material_name,
            "material_base": material_base,
            "material_mod": material_mod,
            "color_name": color_name,
            "color_hex": color_1_hex,
            "diameter_mm": diameter_mm,
            "target_weight": target_weight,
            "print_temp": print_temp,
            "bed_temp": bed_temp,
            "density": density,
        }

        # Parse color 2 using helper method
        color_2_hex = self._parse_rgba_to_hex(octets, 0x52)
        if color_2_hex:
            result["color_2_hex"] = color_2_hex

        # Parse color 3 using helper method
        color_3_hex = self._parse_rgba_to_hex(octets, 0x56)
        if color_3_hex:
            result["color_3_hex"] = color_3_hex

        # Parse online data URL (32 bytes ASCII) at 0x6D
        if len(octets) >= 0x6D + 32:
            online_url = (
                octets[0x6D:0x8D].decode("ascii", errors="ignore").rstrip("\x00")
            )
            if online_url:
                result["online_data_url"] = online_url

        # Parse extended fields if available (NTAG215/216)
        # Extended fields start at 0xA0
        if len(octets) >= 0xA0 + 16:
            # Parse serial number / batch ID (16 bytes UTF-8) at 0xA0
            serial = octets[0xA0:0xB0].decode("utf-8", errors="ignore").rstrip("\x00")
            if serial:
                result["serial"] = serial

        if len(octets) >= 0xB0 + 4:
            # Parse manufacture date (4 bytes: year, year, month, day) at 0xB0
            mfg_year = int.from_bytes(octets[0xB0:0xB2], byteorder="big")
            mfg_month = octets[0xB2]
            mfg_day = octets[0xB3]
            if mfg_year > 0 and mfg_month > 0 and mfg_day > 0:
                result["mfg_date"] = f"{mfg_year:04d}-{mfg_month:02d}-{mfg_day:02d}"

        if len(octets) >= 0xB4 + 3:
            # Parse manufacture time (3 bytes: hour, minute, second) at 0xB4
            mfg_hour = octets[0xB4]
            mfg_minute = octets[0xB5]
            mfg_second = octets[0xB6]
            if mfg_hour < 24 and mfg_minute < 60 and mfg_second < 60:
                result["mfg_time"] = f"{mfg_hour:02d}:{mfg_minute:02d}:{mfg_second:02d}"

        if len(octets) >= 0xB7 + 1:
            # Parse spool core diameter (1 byte, mm) at 0xB7
            spool_core_diameter = octets[0xB7]
            if spool_core_diameter > 0:
                result["spool_core_diameter"] = spool_core_diameter

        if len(octets) >= 0xB8 + 1:
            # Parse MFI temperature (1 byte, divided by 5) at 0xB8
            mfi_temp_raw = octets[0xB8]
            if mfi_temp_raw > 0:
                result["mfi_temp"] = mfi_temp_raw * 5

        if len(octets) >= 0xB9 + 1:
            # Parse MFI load (1 byte, divided by 10) at 0xB9
            mfi_load_raw = octets[0xB9]
            if mfi_load_raw > 0:
                result["mfi_load"] = mfi_load_raw * 10

        if len(octets) >= 0xBA + 1:
            # Parse MFI value (1 byte, divided by 10) at 0xBA
            mfi_value_raw = octets[0xBA]
            if mfi_value_raw > 0:
                result["mfi_value"] = mfi_value_raw / 10.0

        if len(octets) >= 0xBB + 1:
            # Parse measured tolerance (1 byte, µm) at 0xBB
            measured_tolerance = octets[0xBB]
            if measured_tolerance > 0:
                result["measured_tolerance"] = measured_tolerance

        if len(octets) >= 0xBC + 2:
            # Parse empty spool weight (2 bytes, grams) at 0xBC
            empty_spool_weight = int.from_bytes(octets[0xBC:0xBE], byteorder="big")
            if 0 < empty_spool_weight < 65535:
                result["empty_spool_weight"] = empty_spool_weight

        if len(octets) >= 0xBE + 2:
            # Parse measured filament weight (2 bytes, grams) at 0xBE
            measured_filament_weight = int.from_bytes(
                octets[0xBE:0xC0], byteorder="big"
            )
            if 0 < measured_filament_weight < 65535:
                result["measured_filament_weight"] = measured_filament_weight

        if len(octets) >= 0xC0 + 2:
            # Parse measured filament length (2 bytes, meters) at 0xC0
            measured_filament_length = int.from_bytes(
                octets[0xC0:0xC2], byteorder="big"
            )
            if 0 < measured_filament_length < 65535:
                result["measured_filament_length"] = measured_filament_length

        if len(octets) >= 0xC2 + 2:
            # Parse transmission distance (2 bytes, µm) at 0xC2
            transmission_distance = int.from_bytes(octets[0xC2:0xC4], byteorder="big")
            if 0 < transmission_distance < 65535:
                result["transmission_distance"] = transmission_distance

        if len(octets) >= 0xC4 + 1:
            # Parse max dry temp (1 byte, divided by 5) at 0xC4
            max_dry_temp_raw = octets[0xC4]
            if max_dry_temp_raw > 0:
                result["max_dry_temp"] = max_dry_temp_raw * 5

        if len(octets) >= 0xC5 + 1:
            # Parse dry time (1 byte, hours) at 0xC5
            dry_time = octets[0xC5]
            if dry_time > 0:
                result["dry_time"] = dry_time

        if len(octets) >= 0xC6 + 1:
            # Parse min print temp (1 byte, divided by 5) at 0xC6
            min_print_temp_raw = octets[0xC6]
            if min_print_temp_raw > 0:
                result["min_print_temp"] = min_print_temp_raw * 5

        if len(octets) >= 0xC7 + 1:
            # Parse max print temp (1 byte, divided by 5) at 0xC7
            max_print_temp_raw = octets[0xC7]
            if max_print_temp_raw > 0:
                result["max_print_temp"] = max_print_temp_raw * 5

        if len(octets) >= 0xC8 + 1:
            # Parse min volumetric speed (1 byte, mm³/s) at 0xC8
            min_vso = octets[0xC8]
            if min_vso > 0:
                result["min_volumetric_speed"] = min_vso

        if len(octets) >= 0xC9 + 1:
            # Parse max volumetric speed (1 byte, mm³/s) at 0xC9
            max_vso = octets[0xC9]
            if max_vso > 0:
                result["max_volumetric_speed"] = max_vso

        if len(octets) >= 0xCA + 1:
            # Parse target volumetric speed (1 byte, mm³/s) at 0xCA
            target_vso = octets[0xCA]
            if target_vso > 0:
                result["target_volumetric_speed"] = target_vso

        return result

    # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    def parse(
        self, ndef_data: Any, identifier: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Parse OpenTag3D tag data and create/match entries in Spoolman

        Args:
            ndef_data: NDEF data structure from the tag
            identifier: Tag identifier string

        Returns:
            Tuple of (spool_id, filament_id) as strings, or (None, None) if not found
        """
        if ndef_data is None:
            return None, None

        # Get raw octets from NDEF data
        # OpenTag3D data is at offset 6 in the NDEF octets
        octets = None
        if hasattr(ndef_data, "octets"):
            try:
                octets = ndef_data.octets[6:]
            except (AttributeError, TypeError, IndexError) as ex:
                logger.debug("Failed to get octets from ndef_data: %s", ex)

        if octets is None:
            logger.debug("Could not get raw octets from NDEF data")
            return None, None

        # Parse OpenTag3D data
        tag_data = self._parse_opentag3d_data(octets)
        if tag_data is None:
            logger.debug("Not an OpenTag3D format tag")
            return None, None

        logger.info(
            "Parsed OpenTag3D tag: manufacturer=%s, material=%s, color=%s",
            tag_data["manufacturer"],
            tag_data["material_name"],
            tag_data["color_name"],
        )

        # Generate filament name from template
        filament_name = self._generate_filament_name(tag_data)
        logger.info("Generated filament name from template: %s", filament_name)

        # Find or create vendor
        vendor_id = self.spoolman_client.find_vendor_by_name(tag_data["manufacturer"])

        if vendor_id is None:
            logger.info("Creating new vendor: %s", tag_data["manufacturer"])
            vendor_id = self.spoolman_client.create_vendor(tag_data["manufacturer"])
            if vendor_id is None:
                logger.error("Failed to create vendor")
                return None, None

        # Find or create filament using vendor, material, and name
        # Material is constructed from base_material and material_modifiers
        material = tag_data["material_name"]
        filament_id = self.spoolman_client.find_filament_by_vendor_material_and_name(
            vendor_id, material, filament_name
        )

        if filament_id is None:
            logger.info(
                "Creating new filament: %s %s", tag_data["manufacturer"], filament_name
            )

            # Build base filament data with required fields
            filament_data = {
                "vendor_id": vendor_id,
                "name": filament_name,
                "material": material,
                "density": tag_data["density"],
                "diameter": tag_data["diameter_mm"],
                "color_hex": tag_data["color_hex"],
            }

            # Build multi_color_hexes if color_2_hex is present
            if "color_2_hex" in tag_data:
                multi_color_hexes = [tag_data["color_hex"]]
                multi_color_hexes.append(tag_data["color_2_hex"])
                if "color_3_hex" in tag_data:
                    multi_color_hexes.append(tag_data["color_3_hex"])
                filament_data["multi_color_hexes"] = multi_color_hexes

            # Apply field mapping from config
            filament_data = self._apply_field_mapping(
                tag_data, self.filament_field_mapping, filament_data
            )

            filament_id = self.spoolman_client.create_filament(filament_data)
            if filament_id is None:
                logger.error("Failed to create filament")
                return None, None

        # Create spool with nfc_id
        logger.info(
            "Creating new spool for filament %s with nfc_id %s", filament_id, identifier
        )

        # Build base spool data
        spool_data = {
            "filament_id": filament_id,
        }

        # Apply field mapping from config
        spool_data = self._apply_field_mapping(
            tag_data, self.spool_field_mapping, spool_data
        )

        # Add nfc_id to extra field
        if "extra" not in spool_data:
            spool_data["extra"] = {}
        spool_data["extra"]["nfc_id"] = f'"{identifier.lower()}"'

        # If remaining_weight wasn't set by mapping, use target_weight as fallback
        if "remaining_weight" not in spool_data:
            spool_data["remaining_weight"] = tag_data.get("measured_weight", 0)
            if "initial_weight" not in spool_data:
                spool_data["initial_weight"] = tag_data.get("target_weight", 0)

        spool_id = self.spoolman_client.create_spool(spool_data)

        if spool_id is None:
            logger.error("Failed to create spool")
            return None, None

        logger.info(
            "Successfully created spool %s and filament %s", spool_id, filament_id
        )
        return str(spool_id), str(filament_id)
