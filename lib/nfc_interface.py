# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Abstract interface for NFC handlers"""

from abc import ABC, abstractmethod
from typing import Callable, Any


class NfcInterface(ABC):
    """Abstract base class for NFC handlers"""

    @abstractmethod
    def set_no_tag_present_callback(
        self, on_nfc_no_tag_present: Callable[[], None]
    ) -> None:
        """Sets a callback that will be called when no tag is present"""

    @abstractmethod
    def set_tag_present_callback(
        self,
        on_nfc_tag_present: Callable[[Any, str], None],
    ) -> None:
        """Sets a callback that will be called when a tag has been read"""

    @abstractmethod
    def write_to_tag(self, spool: int, filament: int) -> bool:
        """Writes spool & filament info to tag. Returns true if worked."""

    @abstractmethod
    def run(self) -> None:
        """Run the NFC handler, won't return"""

    @abstractmethod
    def stop(self) -> None:
        """Call to stop the handler"""
