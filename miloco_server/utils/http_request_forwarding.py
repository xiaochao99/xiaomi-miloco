# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
HTTP Request Forwarding Utility
Provides simple HTTP request forwarding functionality
"""
import httpx
import logging
from typing import Optional, Dict, Any
from miloco_server.middleware.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)


async def forward_request(
    method: str,
    target_url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0
) -> httpx.Response:
    """
    Forward HTTP request to target URL
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        target_url: Target URL
        headers: Request headers
        params: URL query parameters
        json_data: JSON request body
        timeout: Request timeout in seconds
        
    Returns:
        httpx.Response: HTTP response object
        include error http code used by response.raise_for_status()
    Raises:
        httpx.HTTPError: Raised when request fails
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        logger.info("Forwarding %s request to %s", method, target_url)
        try:
            response = await client.request(
                method=method.upper(),
                url=target_url,
                headers=headers,
                params=params,
                json=json_data
            )
            logger.info("Forwarding Service Request forwarded successfully: %s %s - Status: %d",
                       method, target_url, response.status_code)
            return response # include error http code used by response.raise_for_status()
        except Exception as e:
            logger.error("Forwarding Service Request faild: %s - %s", target_url, str(e))
            raise ExternalServiceException(
                f"Forwarding Service faild: {target_url} - {str(e)}") from e

async def forward_get(
    target_url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0
) -> httpx.Response:
    """Forward GET request"""
    return await forward_request("GET", target_url, headers, params, timeout=timeout)


async def forward_post(
    target_url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0
) -> httpx.Response:
    """Forward POST request"""
    return await forward_request("POST", target_url, headers, params=params, json_data=json_data, timeout=timeout)
