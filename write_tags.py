#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

""" A program to write NFC tags from Spoolman's data """

import argparse
import json
import time

import ndef
import nfc
import npyscreen
import requests


SPOOL = "SPOOL"
FILAMENT = "FILAMENT"
NDEF_TEXT_TYPE = "urn:nfc:wkt:T"

parser = argparse.ArgumentParser(
    description="Fetches spools from Spoolman and allows writing info about them to RFID tags.",
)

parser.add_argument("--version", action="version", version="%(prog)s 0.0.1")

# pylint: disable=R0801
parser.add_argument(
    "-d",
    "--nfc-device",
    metavar="device",
    default="ttyAMA0",
    help="Which NFC reader to use, see "
    + "https://nfcpy.readthedocs.io/en/latest/topics/get-started.html#open-a-local-device"
    + " for format",
)

parser.add_argument(
    "-u",
    "--url",
    metavar="URL",
    default="http://mainsailos.local:7912",
    help="URL for the Spoolman installation",
)


args = parser.parse_args()


def record_to_text(record):
    """Translate a json spool object to a readable string"""
    return f"#{record['id']} {record['filament']['vendor']['name']} - {record['filament']['name']}"


class PostList(npyscreen.MultiLineAction):
    """A wrapper for MultiLineAction to call the write_tag function"""

    def actionHighlighted(self, _act_on_this, _key_press):
        """Called when a line is chosen"""
        record = self.parent.records[self.cursor_line]
        self.parent.parentApp.write_tag(record)


class PostSelectForm(npyscreen.FormBaseNew):
    """Simple form for showing the spools"""

    def create(self):
        """Create the forms widgets"""
        self.add(
            npyscreen.ButtonPress,
            name="Exit",
            when_pressed_function=self.exit_app,
        )

        url = args.url + "/api/v1/spool"
        records = requests.get(url, timeout=10)
        self.records = json.loads(records.text)

        self.posts = self.add(
            PostList,
            values=list(map(record_to_text, self.records)),
            name="Choose spools to write",
            scroll_exit=True,
        )

    def exit_app(self):
        """Called when exit is choosen"""
        self.parentApp.switchForm(None)


class TagWritingApp(npyscreen.NPSAppManaged):
    """The npyscreen's main class for the application"""

    def __init__(self):
        super().__init__()
        self.status = ""

    def on_nfc_connect(self, tag, spool: int, filament: int) -> bool:
        """Write given spool/filament ids to the tag"""
        try:
            if tag.ndef and tag.ndef.is_writeable:
                tag.ndef.records = [
                    ndef.TextRecord(f"SPOOL:{spool}\nFILAMENT:{filament}\n")
                ]
            else:
                self.status = "Tag is write protected"
        except Exception as ex:  # pylint: disable=W0718
            print(ex)
            self.status = "Got error while writing"
        return False

    def write_tag(self, record):
        """Write the choosen records's data to the tag"""

        npyscreen.notify("Writing " + record_to_text(record), title="Writing to tag")

        spool = record["id"]
        filament = record["filament"]["id"]

        self.status = "Written"

        clf = nfc.ContactlessFrontend(args.nfc_device)
        clf.connect(
            rdwr={"on-connect": lambda tag: self.on_nfc_connect(tag, spool, filament)}
        )
        clf.close()
        npyscreen.notify(self.status, title="Writing to tag")
        time.sleep(1)

    def onStart(self):
        """Called when application starts, just add the form"""
        form = self.addForm(
            "MAIN",
            PostSelectForm,
            name="Choose spool, press enter to write to tag",
        )
        form.set_editing(form.posts)


if __name__ == "__main__":
    app = TagWritingApp()
    app.run()
