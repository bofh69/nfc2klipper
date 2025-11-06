# SPDX-FileCopyrightText: 2025 2024 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

.SILENT:

VENV:=venv
VENV_TIMESTAMP:=$(VENV)/.timestamp
PIP:=$(VENV)/bin/pip3
BLACK:=$(VENV)/bin/black
PYLINT:=$(VENV)/bin/pylint
REUSE:=$(VENV)/bin/reuse
MYPY:=$(VENV)/bin/mypy

SRC=$(wildcard *.py lib/*.py)

help:
	@echo Available targets:
	@echo fmt - formats the python files.
	@echo lint - check the python files with pylint.
	@echo typecheck - check type annotations with mypy.
	@echo run-mock - run nfc2klipper.py with mock objects for testing.
	@echo clean - remove venv directory.

$(VENV_TIMESTAMP): requirements.txt
	@echo Building $(VENV)
	python3 -m venv $(VENV)
	$(PIP) install -r $<
	touch $@

$(BLACK): $(VENV_TIMESTAMP)
	$(PIP) install black

$(PYLINT): $(VENV_TIMESTAMP)
	$(PIP) install pylint

$(REUSE): $(VENV_TIMESTAMP)
	$(PIP) install reuse

$(MYPY): $(VENV_TIMESTAMP)
	$(PIP) install mypy types-toml types-requests

fmt: $(BLACK)
	$(BLACK) $(SRC)

lint: $(PYLINT)
	$(PYLINT) $(SRC)

typecheck: $(MYPY)
	$(MYPY) $(SRC)

reuse: $(REUSE)
	$(REUSE) lint

run-mock:
	@echo "Starting nfc2klipper.py with mock objects..."
	NFC2KLIPPER_USE_MOCKS=1 python3 nfc2klipper.py

clean:
	@rm -rf $(VENV) 2>/dev/null

.PHONY: clean fmt lint typecheck reuse run-mock
