# SPDX-FileCopyrightText: 2024-2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""NFC tag handling"""

import time
import logging
from threading import Lock, Event
from typing import Callable, Optional, Any

import ndef
import nfc
from pn5180_tagomatic import (
    Card,
    ISO15693Error,
    PN5180,
    PN5180Error,
)
from nfc.clf import RemoteTarget

from lib.nfc_parsers import SPOOL, FILAMENT
from lib.nfc_interface import NfcInterface

logger: logging.Logger = logging.getLogger(__name__)


# pylint: disable=R0902
class NfcpyHandler(NfcInterface):
    """NFC Tag handling using nfcpy library"""

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


class PN5180Handler(NfcInterface):
    """NFC Tag handling using nfcpy library"""

    def __init__(self, tty_path: str) -> None:
        self._status: str = ""
        self._tty_path: str = tty_path
        self._on_nfc_no_tag_present: Optional[Callable[[], None]] = None
        self._on_nfc_tag_present: Optional[Callable[[Any, str], None]] = None
        self._should_stop_event: Event = Event()

    def set_no_tag_present_callback(
        self, on_nfc_no_tag_present: Callable[[], None]
    ) -> None:
        """Sets a callback that will be called when no tag is present"""
        self._on_nfc_no_tag_present = on_nfc_no_tag_present

    def set_tag_present_callback(
        self,
        on_nfc_tag_present: Callable[[Any, str], None],
    ) -> None:
        """Sets a callback that will be called when a tag has been read"""
        self._on_nfc_tag_present = on_nfc_tag_present

    def write_to_tag(self, spool: int, filament: int) -> bool:
        """Writes spool & filament info to tag. Returns true if worked."""

        # This wasn't a good idea in the first place, so
        # new users should write the UID to Spoolman instead.
        raise NotImplementedError("Not supported by this reader")

    def _handle_iso14443a_cards(self, reader) -> bool:
        # ISO 14443A cards:
        with reader.start_session(0x00, 0x80) as session:
            uids = session.get_all_iso14443a_uids(True, True)
            if len(uids) > 1:
                logger.warning(
                    "Read more than one ISO 14443A card in field, using first"
                )
            if len(uids) >= 1:
                card = session.connect_iso14443a(uids[0])
                self._read_from_card(card, True)
                return True
        return False

    def _handle_iso15693_cards(self, reader):
        with reader.start_session(0x0D, 0x8D) as session:
            uids = session.iso15693_inventory()
            if len(uids) > 1:
                logger.warning(
                    "Read more than one ISO 15693 card in field, using first"
                )
            if len(uids) >= 1:
                card = session.connect_iso15693(uids[0])
                self._read_from_card(card, False)
                return True
        return False

    def _run_loop(self):
        with PN5180(self._tty_path) as reader:
            while not self._should_stop_event.is_set():
                any_card = False
                any_card = any_card or self._handle_iso14443a_cards(reader)
                any_card = any_card or self._handle_iso15693_cards(reader)
                if not any_card:
                    if self._on_nfc_no_tag_present:
                        self._on_nfc_no_tag_present()
                # Lets not hog the CPU
                time.sleep(0.2)

    def run(self) -> None:
        """Run the NFC handler, won't return"""
        # Open NFC reader. Will throw an exception if it fails.
        while not self._should_stop_event.is_set():
            try:
                self._run_loop()
            except TimeoutError as ex:
                logger.exception(ex)
            except ValueError as ex:
                logger.exception(ex)
            except PN5180Error as ex:
                logger.exception(ex)
            except ISO15693Error as ex:
                logger.exception(ex)
            except Exception as ex:  # pylint: disable=broad-exception-caught
                logger.exception(ex)
                raise

    def stop(self) -> None:
        """Call to stop the handler"""
        self._should_stop_event.set()

    class _Tag:  # pylint: disable=too-few-public-methods
        def __init__(self, card):
            self._card = card
            self._records = None

        def _read_field(self, mem: bytes, offset: int) -> tuple[int, int | None]:
            if offset >= len(mem):
                return (-1, None)
            val = mem[offset]
            offset += 1
            if val < 255:
                return (val, offset)
            if offset + 2 > len(mem):
                return (-1, None)
            val = (mem[offset] << 8) | mem[offset + 1]
            offset += 2
            return (val, offset)

        def _find_ndef_offset(self, mem: bytes) -> int | None:
            if len(mem) < 32:
                return None
            if mem[12] != 0xE1:
                return None
            offset: int | None = 16
            while offset is not None and offset < len(mem):
                (typ, new_offset) = self._read_field(mem, offset)
                if new_offset is None:
                    return None
                offset = new_offset
                if typ == 0x00:
                    continue
                (length, new_offset) = self._read_field(mem, offset)
                if new_offset is None:
                    return None
                offset = new_offset
                if typ == 0x03:
                    break
                offset += length
            if offset is None or offset >= len(mem):
                return None

            return offset

        @property
        def records(self) -> list[ndef.Record]:
            """Return parsed NDEF Records"""
            if self._records is None:
                mem = b""
                try:
                    offset = 0
                    while True:
                        # print(f"Reading from offset {offset}")
                        chunk = self._card.read_memory(offset, 64)
                        if len(chunk) == 0:
                            break
                        offset += len(chunk)
                        mem += chunk
                except TimeoutError:
                    pass

                ndef_offset = self._find_ndef_offset(mem)
                if ndef_offset is not None:
                    self._records = list(ndef.message_decoder(mem[ndef_offset:]))
                else:
                    self._records = []
            return self._records

    def _read_from_card(self, card: Card, parse_ndef: bool) -> None:
        """Read data from tag and call callback"""
        if self._on_nfc_tag_present:
            identifier: str = card.id.uid_as_string()

            if parse_ndef:
                tag = self._Tag(card)
                self._on_nfc_tag_present(tag, identifier)
            else:
                mem = b""
                try:
                    offset = 0
                    while True:
                        # print(f"Reading from offset {offset}")
                        chunk = card.read_memory(offset, 64)
                        offset += len(chunk)
                        mem += chunk
                except TimeoutError:
                    pass
                self._on_nfc_tag_present(mem, identifier)


def create_nfc_handler(nfc_device: str, implementation: str = "nfcpy") -> NfcInterface:
    """Factory function to create the appropriate NFC handler implementation.

    Args:
        nfc_device: Device path for the NFC reader
        implementation: Name of the implementation to use (default: "pn532")

    Returns:
        An instance of NfcInterface

    Raises:
        ValueError: If the requested implementation is not supported
    """
    if implementation == "nfcpy":
        return NfcpyHandler(nfc_device)
    if implementation == "pn5180":
        return PN5180Handler(nfc_device)

    # Placeholder for future implementations like "pn5180-tagomatic"
    raise ValueError(
        f"Unknown NFC implementation: '{implementation}'. "
        "Currently only 'nfcpy' is supported."
    )
