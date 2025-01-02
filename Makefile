# SPDX-FileCopyrightText: 2025 2024 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

.SILENT:

VENV:=venv
VENV_TIMESTAMP:=$(VENV)/.timestamp
PIP:=$(VENV)/bin/pip3
BLACK:=$(VENV)/bin/black
PYLINT:=$(VENV)/bin/pylint

SRC=$(wildcard *.py lib/*.py)

help:
	@echo Available targets:
	@echo fmt - formats the python files.
	@echo lint - check the python files with pylint.
	@echo clean - remove venv directory.

$(VENV_TIMESTAMP): requirements.txt
	@echo Building $(VENV)
	virtualenv -p python3 $(VENV)
	$(PIP) install -r $<
	touch $@

$(BLACK): $(VENV_TIMESTAMP)
	$(PIP) install black

$(PYLINT): $(VENV_TIMESTAMP)
	$(PIP) install pylint

fmt: $(BLACK)
	$(BLACK) $(SRC)

lint: $(PYLINT)
	$(PYLINT) $(SRC)

clean:
	@rm -rf $(VENV) 2>/dev/null

.PHONY: clean fmt lint
