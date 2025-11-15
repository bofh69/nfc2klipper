# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tag parsers for different data formats"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional, Protocol, Tuple

import ndef

# Add open_print_tag utils to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "open_print_tag", "utils")
)
from record import Record
from common import default_config_file

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


class OpenPrintTagParser:
    """Parser for OpenPrintTag format tags

    This parser reads tags using the OpenPrintTag format specification.
    It extracts material information from the tag and automatically creates
    vendor, filament, and spool entries in Spoolman with the NFC tag identifier.

    Field mappings and name templates are configured via the [openprint_tag]
    section in nfc2klipper.cfg
    """

    def __init__(self, spoolman_client: Any, config: Dict[str, Any]) -> None:
        """Initialize with a Spoolman client instance

        Args:
            spoolman_client: Client object with methods to create/update Spoolman entries
            config: Configuration dictionary from nfc2klipper.cfg
        """
        self.spoolman_client = spoolman_client
        self.config = config.get("openprint_tag", {})

        # Set defaults if not in config
        if not self.config:
            self.config = {
                "vendor_name_field": "brand_name",
                "filament_name_template": "{material_name}",
                "material_field": "material_type",
                "density_field": "density",
                "diameter_field": "filament_diameter",
                "diameter_default": 1.75,
                "weight_field": "actual_netto_full_weight",
                "weight_fallback": "nominal_netto_full_weight",
                "spool_weight_field": "empty_container_weight",
                "color_field": "primary_color",
                "extruder_temp_min_field": "min_print_temperature",
                "extruder_temp_max_field": "max_print_temperature",
                "bed_temp_min_field": "min_bed_temperature",
                "bed_temp_max_field": "max_bed_temperature",
            }

    def _get_field_value(
        self, data: Dict[str, Any], field_name: Optional[str], default: Any = None
    ) -> Any:
        """Get a field value from data with optional default"""
        if field_name is None:
            return default
        return data.get(field_name, default)

    def _get_avg_temp(
        self, data: Dict[str, Any], min_field: Optional[str], max_field: Optional[str]
    ) -> Optional[int]:
        """Get average temperature from min/max fields"""
        min_temp = self._get_field_value(data, min_field)
        max_temp = self._get_field_value(data, max_field)

        if min_temp is not None and max_temp is not None:
            return int((min_temp + max_temp) / 2)
        if min_temp is not None:
            return int(min_temp)
        if max_temp is not None:
            return int(max_temp)
        return None

    def _format_filament_name(self, data: Dict[str, Any]) -> str:
        """Format filament name using template from config"""
        template = self.config.get("filament_name_template", "{material_name}")
        # Replace {field_name} placeholders with actual values
        result = template
        for key, value in data.items():
            placeholder = "{" + key + "}"
            if placeholder in result and value is not None:
                result = result.replace(placeholder, str(value))
        return result

    def _rgb_to_hex(self, rgb_bytes: bytes) -> str:
        """Convert RGB(A) bytes to hex color string"""
        if len(rgb_bytes) >= 3:
            return f"{rgb_bytes[0]:02x}{rgb_bytes[1]:02x}{rgb_bytes[2]:02x}"
        return "000000"

    def parse(
        self, ndef_data: Any, identifier: str
    ) -> Tuple[Optional[str], Optional[str]]:
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        # This method is complex due to the nature of parsing OpenPrintTag tags
        """Parse OpenPrintTag tag data and create Spoolman entries

        Args:
            ndef_data: NDEF data structure from the tag (can be None)
            identifier: Tag identifier string

        Returns:
            Tuple of (spool_id, filament_id) as strings, or (None, None) if not found
        """
        if ndef_data is None:
            return None, None

        try:
            # Look for OpenPrintTag NDEF records
            for record in ndef_data.records:
                if (
                    hasattr(record, "type")
                    and record.type == "application/vnd.openprinttag"
                ):
                    try:
                        # Parse the OpenPrint3D record
                        opt_record = Record(
                            default_config_file, memoryview(record.data)
                        )

                        # Extract data from the main region
                        if not opt_record.main_region:
                            continue

                        data = opt_record.main_region.read()

                        # Extract vendor/brand information using config
                        vendor_name_field = self.config.get(
                            "vendor_name_field", "brand_name"
                        )
                        brand_name = self._get_field_value(
                            data, vendor_name_field, "Unknown Brand"
                        )

                        # Format filament name using template
                        filament_name = self._format_filament_name(data)

                        # Extract material type using config
                        material_field = self.config.get("material_field")
                        material_type = self._get_field_value(
                            data, material_field, "PLA"
                        )

                        # Extract physical properties using config
                        density_field = self.config.get("density_field")
                        density = self._get_field_value(data, density_field)

                        diameter_field = self.config.get("diameter_field")
                        diameter_default = self.config.get("diameter_default", 1.75)
                        diameter = self._get_field_value(
                            data, diameter_field, diameter_default
                        )

                        # Extract weight information using config
                        weight_field = self.config.get("weight_field")
                        weight_fallback = self.config.get("weight_fallback")
                        weight = self._get_field_value(
                            data, weight_field
                        ) or self._get_field_value(data, weight_fallback)

                        spool_weight_field = self.config.get("spool_weight_field")
                        spool_weight = self._get_field_value(data, spool_weight_field)

                        # Extract temperature information using config
                        extruder_temp = self._get_avg_temp(
                            data,
                            self.config.get("extruder_temp_min_field"),
                            self.config.get("extruder_temp_max_field"),
                        )

                        bed_temp = self._get_avg_temp(
                            data,
                            self.config.get("bed_temp_min_field"),
                            self.config.get("bed_temp_max_field"),
                        )

                        # Extract color information using config
                        color_hex = None
                        color_field = self.config.get("color_field")
                        if color_field:
                            primary_color = data.get(color_field)
                            if (
                                primary_color
                                and isinstance(primary_color, dict)
                                and "hex" in primary_color
                            ):
                                hex_str = primary_color["hex"]
                                # Convert hex string to RGB hex color (first 6 chars for RGB)
                                if len(hex_str) >= 6:
                                    color_hex = hex_str[:6]

                        logger.info(
                            "Found OpenPrintTag tag: brand=%s, material=%s, type=%s",
                            brand_name,
                            filament_name,
                            material_type,
                        )

                        # Create or get vendor
                        vendor = self.spoolman_client.get_or_create_vendor(brand_name)
                        vendor_id = vendor["id"]

                        # Build filament data structure according to Spoolman API
                        filament_data: Dict[str, Any] = {
                            "name": filament_name,
                            "vendor_id": vendor_id,
                        }

                        if material_type:
                            filament_data["material"] = material_type

                        if density is not None:
                            filament_data["density"] = density

                        # Spoolman uses arrays for weights and diameters
                        if weight is not None or spool_weight is not None:
                            weight_obj: Dict[str, Any] = {}
                            if weight is not None:
                                weight_obj["weight"] = weight
                            if spool_weight is not None:
                                weight_obj["spool_weight"] = spool_weight
                            filament_data["weights"] = [weight_obj]

                        if diameter is not None:
                            filament_data["diameters"] = [diameter]

                        if color_hex:
                            # Ensure hex is properly formatted
                            if color_hex.startswith("#"):
                                color_hex = color_hex[1:]
                            filament_data["colors"] = [{"hex": f"#{color_hex}"}]

                        if extruder_temp is not None:
                            filament_data["extruder_temp"] = extruder_temp

                        if bed_temp is not None:
                            filament_data["bed_temp"] = bed_temp

                        # Create filament
                        filament = self.spoolman_client.create_filament(filament_data)
                        filament_id = filament["id"]

                        # Build spool data structure according to Spoolman API
                        spool_data: Dict[str, Any] = {
                            "filament_id": filament_id,
                            "extra": {"nfc_id": f'"{identifier.lower()}"'},
                        }

                        # Create spool with NFC ID
                        spool = self.spoolman_client.create_spool(spool_data)
                        spool_id = spool["id"]

                        logger.info(
                            "Created spool_id=%s, filament_id=%s for OpenPrintTag tag",
                            spool_id,
                            filament_id,
                        )

                        return str(spool_id), str(filament_id)

                    except Exception as ex:  # pylint: disable=broad-except
                        logger.warning("Could not parse OpenPrintTag record: %s", ex)

        except ImportError:
            logger.debug("OpenPrintTag parsing libraries not available")
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning("Error parsing OpenPrintTag tag: %s", ex)

        return None, None
