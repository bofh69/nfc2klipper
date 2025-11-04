# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# To build the Docker image, update nfc2klipper.cfg and use the following command:
# docker build -t nfc2klipper .

# To run the container with access to /dev/ttyAMA0, use the following command:
# docker run --device /dev/ttyAMA0:/dev/ttyAMA0 --net=host --name nfc2klipper_app nfc2klipper

# Note: Ensure that your user has the necessary permissions to access /dev/ttyAMA0 on the host system.


FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    patch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /nfc2klipper
COPY ["requirements.txt", "." ]
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir -r requirements.txt
COPY ["pn532.py.patch",  "nfc2klipper.*", "./"]
COPY [ "templates", "templates/" ]
COPY [ "lib", "lib/" ]

# Patch nfcpy:
RUN patch -p6 /usr/local/lib/python3.*/site-packages/nfc/clf/pn532.py < pn532.py.patch

# Install config file:
RUN mkdir -p /root/.config/nfc2klipper
RUN cp nfc2klipper.cfg /root/.config/nfc2klipper/

ENTRYPOINT [ "./nfc2klipper.py" ]
