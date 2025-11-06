# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""NFC tag handling"""

import time
import logging
from threading import Lock, Event
from typing import Callable, Optional, Tuple, List

import ndef
import nfc
from nfc.clf import RemoteTarget


SPOOL: str = "SPOOL"
FILAMENT: str = "FILAMENT"
NDEF_TEXT_TYPE: str = "urn:nfc:wkt:T"

logger: logging.Logger = logging.getLogger(__name__)


# pylint: disable=R0902
class NfcHandler:
    """NFC Tag handling"""

    def __init__(self, nfc_device: str) -> None:
        self.status: str = ""
        self.nfc_device: str = nfc_device
        self.on_nfc_no_tag_present: Optional[Callable[[], None]] = None
        self.on_nfc_tag_present: Optional[
            Callable[[Optional[str], Optional[str], str], None]
        ] = None
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
        on_nfc_tag_present: Callable[[Optional[str], Optional[str], str], None],
    ) -> None:
        """Sets a callback that will be called when a tag has been read"""
        self.on_nfc_tag_present = on_nfc_tag_present

    @classmethod
    def get_data_from_ndef_records(
        cls, records: List[ndef.TextRecord]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Find wanted data from the NDEF records.

        >>> import ndef
        >>> record0 = ndef.TextRecord("")
        >>> record1 = ndef.TextRecord("SPOOL:23\\n")
        >>> record2 = ndef.TextRecord("FILAMENT:14\\n")
        >>> record3 = ndef.TextRecord("SPOOL:23\\nFILAMENT:14\\n")
        >>> NfcHandler.get_data_from_ndef_records([record0])
        (None, None)
        >>> NfcHandler.get_data_from_ndef_records([record3])
        ('23', '14')
        >>> NfcHandler.get_data_from_ndef_records([record1])
        ('23', None)
        >>> NfcHandler.get_data_from_ndef_records([record2])
        (None, '14')
        >>> NfcHandler.get_data_from_ndef_records([record0, record3])
        ('23', '14')
        >>> NfcHandler.get_data_from_ndef_records([record3, record0])
        ('23', '14')
        >>> NfcHandler.get_data_from_ndef_records([record1, record2])
        ('23', '14')
        >>> NfcHandler.get_data_from_ndef_records([record2, record1])
        ('23', '14')
        """

        spool: Optional[str] = None
        filament: Optional[str] = None

        for record in records:
            if record.type == NDEF_TEXT_TYPE:
                for line in record.text.splitlines():
                    line = line.split(":")
                    if len(line) == 2:
                        if line[0] == SPOOL:
                            spool = line[1]
                        if line[0] == FILAMENT:
                            filament = line[1]
            else:
                logger.info("Read other record: %s", record)

        return spool, filament

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
            if self.write_spool:
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
            spool: Optional[str]
            filament: Optional[str]
            spool, filament = NfcHandler.get_data_from_ndef_records(tag.ndef.records)
            identifier: str
            if tag.identifier:
                identifier = ":".join(f"{byte:x}" for byte in tag.identifier)
            else:
                identifier = "<undefined>"
            self.on_nfc_tag_present(spool, filament, identifier)
