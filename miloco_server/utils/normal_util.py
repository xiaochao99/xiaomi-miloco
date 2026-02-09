# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Normal utility functions for common operations.
Provides functionality for logging configuration, certificate management, and JSON extraction.
"""

import base64
import datetime
import ipaddress
import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from miloco_server.config.normal_config import APP_CONFIG, SERVER_CONFIG, LOG_DIR

logger = logging.getLogger(name=__name__)


def get_uvicorn_log_config(enable_file_logging: Optional[bool] = None,
                           enable_console_logging: Optional[bool] = None):
    """
    Get uvicorn log configuration

    Args:
        enable_file_logging: Whether to enable file logging, if None then read from config
        enable_console_logging: Whether to enable console logging, if None then read from config
    """
    # Get configuration parameters
    log_level = SERVER_CONFIG["log_level"].upper()
    file_logging = (SERVER_CONFIG.get("enable_file_logging", True)
                    if enable_file_logging is None else enable_file_logging)
    console_logging = (SERVER_CONFIG.get("enable_console_logging", True)
                       if enable_console_logging is None else enable_console_logging)

    # Build handlers
    handlers = {}
    handler_list = []

    if console_logging:
        handlers["console"] = {"class": "logging.StreamHandler", "formatter": "default", "level": log_level}
        handler_list.append("console")

    if file_logging:
        # Create log file
        log_dir = str(LOG_DIR)
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        service_name = APP_CONFIG["service_name"]
        log_filename = os.path.join(log_dir, f"{service_name}_{timestamp}.log")

        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": log_filename,
            "mode": "a",
            "formatter": "default",
            "level": log_level,
            "encoding": "utf-8"
        }
        handler_list.append("file")

    # Basic log configuration
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            }
        },
        "handlers": handlers,
        "root": {"level": log_level, "handlers": handler_list},
        "loggers": {
            "uvicorn": {"level": log_level, "handlers": handler_list, "propagate": False},
            "uvicorn.access": {"level": log_level, "handlers": handler_list, "propagate": False},
            "uvicorn.error": {"level": log_level, "handlers": handler_list, "propagate": False}
        }
    }


def _generate_localhost_cert(cert_path: str, key_path: str, years_valid: int, country_name: str = "CN"):
    """Generate a self-signed certificate for localhost."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Xiaomi Home AI Assistant"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    valid_from = datetime.datetime.now(datetime.timezone.utc)
    valid_to = valid_from + datetime.timedelta(days=365 * years_valid)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(valid_to)
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")),
                x509.IPAddress(ipaddress.IPv6Address("::1")),
            ]),
            critical=False
        ).sign(key, hashes.SHA256())
    )

    # Save private key.
    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Save certificate.
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    logger.info("generate localhost cert success, %s, %s", cert_path, key_path)


def update_localhost_cert(cert_path: str, key_path: str, years_valid: int = 10, country_name: str = "CN"):
    """Generate a self-signed certificate for localhost."""

    # Check if the certificate already exists.
    if not os.path.exists(cert_path):
        logger.info("cert not exist, generate new cert")
        if not Path(cert_path).parent.exists():
            os.makedirs(Path(cert_path).parent, exist_ok=True)
        _generate_localhost_cert(
            cert_path=cert_path, key_path=key_path, years_valid=years_valid, country_name=country_name)
        return

    # Read the certificate.
    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    except Exception as e:
        raise RuntimeError(f"cert read error: {e}") from e

    # Get the current time.
    now = datetime.datetime.now(datetime.timezone.utc)

    # Check if the certificate is expired.
    if cert.not_valid_after_utc < now:
        cn = None
        try:
            cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except IndexError as e:
            raise RuntimeError("certificate not valid, CN not found") from e

        if cn.lower() == "localhost":
            logger.info("certificate expired, CN=%s, re-generate", cn)
            _generate_localhost_cert(
                cert_path=cert_path, key_path=key_path, years_valid=years_valid, country_name=country_name)
        else:
            raise RuntimeError(f"certificate expired, CN={cn}, not localhost, not re-generate")
    else:
        logger.info("cert valid, not re-generate, expired at %s", cert.not_valid_after_utc)


def bytes_to_base64(image_data: bytes) -> str:
    """
    Convert image binary data to base64 format

    Args:
        image_data: Image binary data

    Returns:
        Base64 encoded image string
    """
    encoded_data = base64.b64encode(image_data).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded_data}"


def read_last_n_lines(file_path: str, n: int) -> List[str]:
    """
    Read the last n lines of a file

    Args:
        file_path: File path
        n: Number of lines to read

    Returns:
        List[str]: List of the last n lines of the file
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        # Get the last n lines, if file has fewer than n lines, return all lines
        return lines[-n:] if len(lines) >= n else lines


# Pre-compile regex patterns to avoid recompilation on each call
_JSON_MARKDOWN_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_BRACES_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_from_content(content: str) -> str:
    """
    Extract JSON string from LLM returned content
    Handle cases that may contain markdown code blocks or other text
    """
    # Remove leading and trailing whitespace
    content = content.strip()

    # Try to extract JSON from markdown code blocks (using pre-compiled regex)
    json_match = _JSON_MARKDOWN_PATTERN.search(content)
    if json_match:
        return json_match.group(1).strip()

    # Try to extract JSON surrounded by braces (using pre-compiled regex)
    json_match = _JSON_BRACES_PATTERN.search(content)
    if json_match:
        return json_match.group(0).strip()

    # If no JSON format found, return original content
    return content
