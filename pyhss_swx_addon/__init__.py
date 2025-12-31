"""
PyHSS SWx Addon
===============

Implements the 3GPP SWx Diameter interface for non-3GPP access (WiFi Calling)

Usage:
    from pyhss_swx_addon import init_swx
    
    swx_handler = init_swx(diameter, database, yaml_config, redis_store)

Author: PyHSS Community
License: AGPL-3.0
"""

from .swx_init import (
    init_swx,
    patch_hss_service,
    create_swx_tables,
    get_swx_config,
    validate_swx_config,
    SWxIntegration,
    SWX_APPLICATION_ID,
    SWX_ADDON_VERSION,
    SWX_ADDON_NAME
)

__version__ = SWX_ADDON_VERSION
__all__ = [
    'init_swx',
    'patch_hss_service',
    'create_swx_tables',
    'get_swx_config',
    'validate_swx_config',
    'SWxIntegration',
    'SWX_APPLICATION_ID',
    'SWX_ADDON_VERSION',
    'SWX_ADDON_NAME'
]
