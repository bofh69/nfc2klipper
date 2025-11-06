#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Sebastian Andersson <sebastian@bittr.nu>
# SPDX-License-Identifier: GPL-3.0-or-later

"""IPC (Inter-Process Communication) module for Unix domain socket communication."""

import inspect
import json
import logging
import os
import socket
import sys
from typing import Any, Callable, Dict

logger: logging.Logger = logging.getLogger(__name__)


class IPCClient:  # pylint: disable=R0903
    """Client for sending requests via Unix domain socket"""

    def __init__(self, socket_path: str) -> None:
        """Initialize IPC client with socket path"""
        self.socket_path: str = socket_path

    def send_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the server via Unix domain socket"""
        try:
            client: socket.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.socket_path)
            client.sendall(json.dumps(request_data).encode("utf-8"))
            response: str = client.recv(65536).decode("utf-8")
            client.close()
            return json.loads(response)
        except Exception as ex:  # pylint: disable=W0718
            logger.error("Error communicating with server: %s", ex)
            return {"status": "error", "message": str(ex)}


class IPCServer:
    """Server for handling requests via Unix domain socket"""

    def __init__(self, socket_path: str) -> None:
        """Initialize IPC server with socket path"""
        self.socket_path: str = socket_path
        self.request_handlers: Dict[str, Callable[..., Dict[str, Any]]] = {}

    def register_handler(
        self, command_name: str
    ) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
        """Decorator to register a request handler for a specific command"""

        def decorator(
            func: Callable[..., Dict[str, Any]]
        ) -> Callable[..., Dict[str, Any]]:
            self.request_handlers[command_name] = func
            return func

        return decorator

    def handle_request(self, request_data: str) -> Dict[str, Any]:
        """Handle a request from a client"""
        try:
            request = json.loads(request_data)
            command = request.get("command")

            # Look up the handler for this command
            if command in self.request_handlers:
                handler = self.request_handlers[command]
                # Extract arguments based on handler function signature
                sig = inspect.signature(handler)
                kwargs = {}
                for param_name in sig.parameters:
                    if param_name in request:
                        kwargs[param_name] = request[param_name]
                return handler(**kwargs)

            return {"status": "error", "message": f"Unknown command: {command}"}

        except Exception as ex:  # pylint: disable=W0718
            logger.exception("Error handling request: %s", ex)
            return {"status": "error", "message": str(ex)}

    def start(self) -> None:
        """Start the Unix domain socket server"""
        # Ensure the directory for the socket exists
        socket_dir: str = os.path.dirname(self.socket_path)
        if socket_dir and not os.path.exists(socket_dir):
            try:
                os.makedirs(socket_dir, exist_ok=True)
                logger.info("Created socket directory: %s", socket_dir)
            except OSError as ex:
                logger.error(
                    "ERROR: Failed to create directory for socket: %s\n"
                    "  Directory: %s\n"
                    "  Error: %s\n"
                    "  Fix: Ensure the parent directory exists and "
                    "you have write permissions.\n"
                    "       You can also change the socket_path in the "
                    "config file [webserver] section.",
                    self.socket_path,
                    socket_dir,
                    ex,
                )
                sys.exit(1)

        # Remove socket file if it exists
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError as ex:
                logger.error(
                    "ERROR: Failed to remove existing socket file: %s\n"
                    "  Socket: %s\n"
                    "  Error: %s\n"
                    "  Fix: Ensure you have write permissions or "
                    "manually remove the file.\n"
                    "       You can also change the socket_path in the "
                    "config file [webserver] section.",
                    self.socket_path,
                    self.socket_path,
                    ex,
                )
                sys.exit(1)

        try:
            server: socket.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(self.socket_path)
            server.listen(5)
            logger.info("Socket server listening on %s", self.socket_path)
        except OSError as ex:
            logger.error(
                "ERROR: Failed to create socket: %s\n"
                "  Socket: %s\n"
                "  Error: %s\n"
                "  Fix: Ensure the directory exists and you have write permissions.\n"
                "       Check if another process is using this socket path.\n"
                "       You can also change the socket_path in the "
                "config file [webserver] section.",
                self.socket_path,
                self.socket_path,
                ex,
            )
            sys.exit(1)

        while True:
            try:
                conn: socket.socket
                conn, _ = server.accept()
                data: str = conn.recv(65536).decode("utf-8")
                if data:
                    response: Dict[str, Any] = self.handle_request(data)
                    conn.sendall(json.dumps(response).encode("utf-8"))
                conn.close()
            except Exception as ex:  # pylint: disable=W0718
                logger.exception("Error in socket server: %s", ex)
