# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""NFC tag handling"""

import time
import logging
from threading import Lock, Event
from typing import Callable, Optional, Any

import ndef
import nfc
from nfc.clf import RemoteTarget

from lib.nfc_parsers import SPOOL, FILAMENT

logger: logging.Logger = logging.getLogger(__name__)


# pylint: disable=R0902
class NfcHandler:
    """NFC Tag handling"""

    def __init__(self, nfc_device: str) -> None:
        self.status: str = ""
        self.nfc_device: str = nfc_device
        self.on_nfc_no_tag_present: Optional[Callable[[], None]] = None
        self.on_nfc_tag_present: Optional[Callable[[Any, str], None]] = None
        self.should_stop_event: Event = Event()
        self.write_lock: Lock = Lock()
        self.write_event: Event = Event()
        self.write_spool: Optional[int] = None
        self.write_filament: Optional[int] = None

    def set_no_tag_present_callback(
        self, on_nfc_no_tag_present: Callable[[], None]
    ) -> None:
        """Sets a callback that will be called when no tag is present"""
        self.on_nfc_no_tag_present = on_nfc_no_tag_present

    def set_tag_present_callback(
        self,
        on_nfc_tag_present: Callable[[Any, str], None],
    ) -> None:
        """Sets a callback that will be called when a tag has been read"""
        self.on_nfc_tag_present = on_nfc_tag_present

    def write_to_tag(self, spool: int, filament: int) -> bool:
        """Writes spool & filament info to tag. Returns true if worked."""

        self._set_write_info(spool, filament)

        if self.write_event.wait(timeout=30):
            return True

        self._set_write_info(None, None)

        return False

    def run(self) -> None:
        """Run the NFC handler, won't return"""
        # Open NFC reader. Will throw an exception if it fails.
        with nfc.ContactlessFrontend(self.nfc_device) as clf:
            while not self.should_stop_event.is_set():
                tag = clf.connect(rdwr={"on-connect": lambda tag: False})
                if tag:
                    self._check_for_write_to_tag(tag)
                    if tag.ndef is None:
                        if self.on_nfc_no_tag_present:
                            self.on_nfc_no_tag_present()
                    else:
                        self._read_from_tag(tag)

                    # Wait for the tag to be removed.
                    while clf.sense(
                        RemoteTarget("106A"), RemoteTarget("106B"), RemoteTarget("212F")
                    ):
                        if self._check_for_write_to_tag(tag):
                            self._read_from_tag(tag)
                        time.sleep(0.2)
                else:
                    time.sleep(0.2)

    def stop(self) -> None:
        """Call to stop the handler"""
        self.should_stop_event.set()

    def _write_to_nfc_tag(self, tag: nfc.tag.Tag, spool: int, filament: int) -> bool:
        """Write given spool/filament ids to the tag"""
        try:
            if tag.ndef and tag.ndef.is_writeable:
                tag.ndef.records = [
                    ndef.TextRecord(f"{SPOOL}:{spool}\n{FILAMENT}:{filament}\n")
                ]
                return True
            self.status = "Tag is write protected"
        except Exception as ex:  # pylint: disable=W0718
            logger.exception(ex)
            self.status = "Got error while writing"
        return False

    def _set_write_info(self, spool: Optional[int], filament: Optional[int]) -> None:
        if self.write_lock.acquire():  # pylint: disable=R1732
            self.write_spool = spool
            self.write_filament = filament
            self.write_event.clear()
            self.write_lock.release()

    def _check_for_write_to_tag(self, tag: nfc.tag.Tag) -> bool:
        """Check if the tag should be written to and do it"""
        did_write: bool = False
        if self.write_lock.acquire():  # pylint: disable=R1732
            if self.write_spool is not None and self.write_filament is not None:
                if self._write_to_nfc_tag(tag, self.write_spool, self.write_filament):
                    self.write_event.set()
                    did_write = True
                self.write_spool = None
                self.write_filament = None
            self.write_lock.release()
        return did_write

    def _read_from_tag(self, tag: nfc.tag.Tag) -> None:
        """Read data from tag and call callback"""
        if self.on_nfc_tag_present:
            identifier: str
            if tag.identifier:
                identifier = ":".join(f"{byte:x}" for byte in tag.identifier)
            else:
                identifier = "<undefined>"
            self.on_nfc_tag_present(tag.ndef, identifier)
