# SPDX-FileCopyrightText: 2024-2026 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tag parsers for different data formats"""

import logging
import os
import re
import sys
from typing import Any, Dict, Optional, Tuple

# Add open_print_tag utils to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "open_print_tag", "utils")
)
from record import Record
from common import default_config_file

logger: logging.Logger = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods


class OpenPrintTagParser:
    """Parser for OpenPrintTag format tags"""

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
            filament_field_mapping: Mapping from Spoolman filament fields to record fields
            spool_field_mapping: Mapping from Spoolman spool fields to record fields
        """
        self.spoolman_client = spoolman_client
        self.filament_name_template = filament_name_template
        self.filament_field_mapping = filament_field_mapping
        self.spool_field_mapping = spool_field_mapping

    def _apply_field_mapping(
        self,
        tag_data: Dict[str, Any],
        field_mapping: Dict[str, str],
        base_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Apply field mapping from data records to Spoolman fields

        Args:
            tag_data: Parsed tag data
            field_mapping: Mapping from Spoolman fields to records fields
            base_data: Optional base dictionary to start with

        Returns:
            Dictionary with mapped fields ready for Spoolman API
        """
        result = base_data.copy() if base_data else {}

        for spoolman_field, record_field in field_mapping.items():
            if record_field in tag_data:
                value = tag_data[record_field]
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
            name = self.filament_name_template.format(tag_data)
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

    def _rgb_to_hex(self, rgb_bytes: bytes) -> str:
        """Convert RGB(A) bytes to hex color string"""
        if len(rgb_bytes) >= 3:
            return f"{rgb_bytes[0]:02x}{rgb_bytes[1]:02x}{rgb_bytes[2]:02x}"
        return "000000"

    # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    def parse(self, data: Any, identifier: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse OpenTag3D tag data and create/match entries in Spoolman

        Args:
            data: bytes of the tags memory
            identifier: Tag identifier string

        Returns:
            Tuple of (spool_id, filament_id) as strings, or (None, None) if not found
        """

        opt_record = Record(default_config_file, memoryview(data))
        tag_data = opt_record.regions["main"].read()
        for k, v in tag_data.items():
            print(f"{k} = {v}")

        # Generate filament name from template
        filament_name = self._generate_filament_name(tag_data)
        logger.info("Generated filament name from template: %s", filament_name)

        # Find or create vendor
        vendor_name = tag_data["brand_name"]
        vendor_id = self.spoolman_client.find_vendor_by_name(vendor_name)

        if vendor_id is None:
            logger.info("Creating new vendor: %s", vendor_name)
            empty_spool_weight = tag_data.get("empty_container_weight", None)
            vendor_id = self.spoolman_client.create_vendor(
                vendor_name, empty_spool_weight
            )
            if vendor_id is None:
                logger.error("Failed to create vendor")
                return None, None

        # Find or create filament using vendor, material, and name
        # Material is constructed from base_material and material_modifiers
        material_type = tag_data["material_type"]
        material_name = tag_data["material_name"]
        filament_id = self.spoolman_client.find_filament_by_vendor_material_and_name(
            vendor_id, material_type, material_name
        )

        if filament_id is None:
            logger.info("Creating new filament: %s %s", vendor_name, filament_name)

            density = 1.24

            if (
                "actual_netto_full_weight" in tag_data
                and "actual_full_length" in tag_data
                and "filament_diameter" in tag_data
            ):
                weight = float(tag_data["actual_netto_full_weight"])
                length = float(tag_data["actual_full_length"]) / 10
                diameter = float(tag_data["filament_diameter"])
                density = weight / (length * ((diameter / 20) ** 2) * 3.14159265359)

            # Build base filament data with required fields
            filament_data = {
                "vendor_id": vendor_id,
                "name": filament_name,
                "material": material_type,
                "density": tag_data.get("density", density),
                "diameter": tag_data["filament_diameter"],
                "color_hex": tag_data["primary_color"][1:],
            }

            # Build multi_color_hexes if color_2_hex is present
            multi_color_hexes = []
            for i in range(5):
                if "secondary_color_" + str(i) in tag_data:
                    multi_color_hexes.append(tag_data["secondary_color_" + str(i)][1:])

            if len(multi_color_hexes) > 0:
                filament_data["multi_color_hexes"] = ",".join(multi_color_hexes)

            # Apply field mapping from config
            filament_data = self._apply_field_mapping(
                tag_data, self.filament_field_mapping, filament_data
            )

            if "remaining_weight" not in filament_data:
                if "nominal_netto_full_weight" in tag_data:
                    filament_data["remaining_weight"] = tag_data[
                        "nominal_netto_full_weight"
                    ]

            if "spool_weight" not in filament_data:
                if "empty_container_weight" in tag_data:
                    filament_data["spool_weight"] = tag_data["empty_container_weight"]

            if "article_number" not in filament_data:
                if "gtin" in tag_data:
                    filament_data["article_number"] = tag_data["gtin"]

            if "settings_extruder_temp" not in filament_data:
                filament_data["settings_extruder_temp"] = self._get_avg_temp(
                    tag_data, "min_print_temperature", "max_print_temperature"
                )

            if "settings_bed_temp" not in filament_data:
                filament_data["settings_bed_temp"] = self._get_avg_temp(
                    tag_data, "min_bed_temperature", "max_bed_temperature"
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

        if "remaining_weight" not in spool_data:
            if "actual_netto_full_weight" in tag_data:
                spool_data["remaining_weight"] = tag_data["actual_netto_full_weight"]

        if "initial_weight" not in spool_data:
            if "actual_netto_full_weight" in tag_data:
                spool_data["initial_weight"] = tag_data["actual_netto_full_weight"]

        spool_id = self.spoolman_client.create_spool(spool_data)

        if spool_id is None:
            logger.error("Failed to create spool")
            return None, None

        logger.info(
            "Successfully created spool %s and filament %s", spool_id, filament_id
        )
        return str(spool_id), str(filament_id)
