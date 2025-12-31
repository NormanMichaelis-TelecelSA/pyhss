"""
PyHSS SWx Addon Integration
Main integration module for adding SWx interface support to PyHSS

This module provides the integration layer between the SWx addon and
the main PyHSS codebase. It handles:
- Initialization of SWx handler
- Registration of SWx API endpoints
- Patching of diameter message routing
- Database table creation

Usage:
    1. Copy addon files to PyHSS directory
    2. Add SWx configuration to config.yaml
    3. Import and call init_swx() in hssService.py
    4. Run database migrations

Author: PyHSS Community
License: AGPL-3.0
"""

import logging
import sys
import os

# Setup logging
logging.basicConfig(level=logging.DEBUG)
swx_init_logger = logging.getLogger('SWxInit')

# SWx Application ID
SWX_APPLICATION_ID = 16777265

# Version info
SWX_ADDON_VERSION = "1.0.0"
SWX_ADDON_NAME = "PyHSS-SWx"


def init_swx(diameter_instance, database_instance, yaml_config, redis_store=None, flask_app=None):
    """
    Initialize SWx addon for PyHSS.
    
    This is the main entry point for integrating the SWx addon.
    Call this from hssService.py after initializing the main components.
    
    Args:
        diameter_instance: Main PyHSS Diameter class instance
        database_instance: PyHSS database module
        yaml_config: PyHSS configuration dictionary
        redis_store: Redis connection (optional)
        flask_app: Flask application for API registration (optional)
        
    Returns:
        SWxHandler instance or None if disabled
    """
    swx_init_logger.info(f"Initializing {SWX_ADDON_NAME} v{SWX_ADDON_VERSION}")
    
    # Check if SWx is enabled in config
    swx_config = yaml_config.get('swx', {})
    if not swx_config.get('enabled', False):
        swx_init_logger.info("SWx interface disabled in configuration")
        return None
    
    try:
        # Import SWx components
        from lib.diameter_swx import DiameterSWx, create_swx_handler
        from services.hss_swx_handler import SWxHandler, process_swx_request
        from api.api_swx import register_swx_api
        
        # Create SWx handler
        swx_handler = SWxHandler(
            diameter_instance=diameter_instance,
            database_instance=database_instance,
            yaml_config=yaml_config,
            redis_store=redis_store
        )
        
        # Register API endpoints if Flask app provided
        if flask_app:
            register_swx_api(flask_app, swx_handler, database_instance)
            swx_init_logger.info("SWx API endpoints registered")
        
        # Register SWx application in diameter routing
        _register_swx_routing(diameter_instance, swx_handler)
        
        swx_init_logger.info("SWx initialization complete")
        return swx_handler
        
    except Exception as e:
        swx_init_logger.error(f"Failed to initialize SWx: {e}", exc_info=True)
        return None


def _register_swx_routing(diameter_instance, swx_handler):
    """
    Register SWx message routing in diameter instance.
    
    This patches the diameter message handling to route SWx messages
    to the SWx handler.
    """
    swx_init_logger.info("Registering SWx message routing")
    
    # Store handler reference
    diameter_instance.swx_handler = swx_handler
    
    # The actual routing will be handled by patching the hssService
    # message processing loop. See patch_hss_service() for details.


def patch_hss_service(hss_service_module, swx_handler):
    """
    Patch hssService.py to add SWx message routing.
    
    This should be called after loading the hss_service module but before
    starting the message processing loop.
    
    Args:
        hss_service_module: The loaded hssService module
        swx_handler: SWxHandler instance
    """
    swx_init_logger.info("Patching hssService for SWx support")
    
    # Store original process function
    if hasattr(hss_service_module, 'process_diameter_message'):
        original_process = hss_service_module.process_diameter_message
        
        def patched_process(packet_vars, avps):
            """Patched message processor with SWx support."""
            app_id = packet_vars.get('ApplicationId')
            
            # Check if this is an SWx message
            if app_id == SWX_APPLICATION_ID:
                from services.hss_swx_handler import process_swx_request
                return process_swx_request(swx_handler, packet_vars, avps)
            
            # Otherwise use original processing
            return original_process(packet_vars, avps)
        
        hss_service_module.process_diameter_message = patched_process
        swx_init_logger.info("hssService patched for SWx routing")


def create_swx_tables(database_instance, yaml_config):
    """
    Create SWx database tables.
    
    This can be called to create tables without running full migrations.
    
    Args:
        database_instance: PyHSS database module
        yaml_config: Configuration dictionary
    """
    swx_init_logger.info("Creating SWx database tables")
    
    try:
        from lib.models_swx import (
            SWX_REGISTRATION, 
            NON_3GPP_SUBSCRIPTION,
            SWX_APN_CONFIGURATION,
            SWX_EMERGENCY_INFO
        )
        
        # Get engine from database
        engine = database_instance.engine
        
        # Import base
        from sqlalchemy.ext.declarative import declarative_base
        Base = declarative_base()
        
        # Create tables
        SWX_REGISTRATION.__table__.create(engine, checkfirst=True)
        NON_3GPP_SUBSCRIPTION.__table__.create(engine, checkfirst=True)
        SWX_APN_CONFIGURATION.__table__.create(engine, checkfirst=True)
        SWX_EMERGENCY_INFO.__table__.create(engine, checkfirst=True)
        
        swx_init_logger.info("SWx tables created successfully")
        return True
        
    except Exception as e:
        swx_init_logger.error(f"Failed to create SWx tables: {e}")
        return False


# ============================================================================
# Configuration Helpers
# ============================================================================

DEFAULT_SWX_CONFIG = {
    'enabled': False,
    'application_id': 16777265,
    'default_apn': 'ims',
    'auth_scheme': 'EAP-AKA',
    'num_auth_vectors': 1,
    'auto_create_non3gpp_subscription': True,
}


def get_swx_config(yaml_config):
    """
    Get SWx configuration with defaults.
    
    Args:
        yaml_config: PyHSS configuration dictionary
        
    Returns:
        Complete SWx configuration dictionary
    """
    swx_config = yaml_config.get('swx', {})
    
    # Merge with defaults
    config = DEFAULT_SWX_CONFIG.copy()
    config.update(swx_config)
    
    return config


def validate_swx_config(yaml_config):
    """
    Validate SWx configuration.
    
    Args:
        yaml_config: PyHSS configuration dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    swx_config = yaml_config.get('swx', {})
    
    if not swx_config.get('enabled', False):
        return True, "SWx disabled"
    
    # Validate auth scheme
    auth_scheme = swx_config.get('auth_scheme', 'EAP-AKA')
    if auth_scheme not in ['EAP-AKA', 'EAP-AKA\'', 'EAP-AKA-PRIME']:
        return False, f"Invalid auth_scheme: {auth_scheme}"
    
    # Validate num_auth_vectors
    num_vectors = swx_config.get('num_auth_vectors', 1)
    if not isinstance(num_vectors, int) or num_vectors < 1 or num_vectors > 5:
        return False, f"num_auth_vectors must be 1-5, got: {num_vectors}"
    
    return True, "Configuration valid"


# ============================================================================
# Diameter Integration Helpers
# ============================================================================

def add_swx_to_cea(diameter_instance):
    """
    Add SWx application to Capabilities-Exchange-Answer.
    
    This should be called to advertise SWx support to Diameter peers.
    
    Args:
        diameter_instance: Main PyHSS Diameter class instance
    """
    # Add SWx to supported applications list
    if hasattr(diameter_instance, 'supported_applications'):
        if SWX_APPLICATION_ID not in diameter_instance.supported_applications:
            diameter_instance.supported_applications.append(SWX_APPLICATION_ID)
            swx_init_logger.info(f"Added SWx Application-ID {SWX_APPLICATION_ID} to supported applications")


def is_swx_message(packet_vars):
    """
    Check if a diameter message is SWx.
    
    Args:
        packet_vars: Decoded packet variables
        
    Returns:
        True if SWx message
    """
    return packet_vars.get('ApplicationId') == SWX_APPLICATION_ID


def get_swx_command_name(command_code, is_request=True):
    """
    Get human-readable SWx command name.
    
    Args:
        command_code: Diameter command code
        is_request: True for request, False for answer
        
    Returns:
        Command name string
    """
    commands = {
        303: ('MAR', 'MAA'),  # Multimedia-Auth
        301: ('SAR', 'SAA'),  # Server-Assignment
        304: ('RTR', 'RTA'),  # Registration-Termination
        305: ('PPR', 'PPA'),  # Push-Profile
    }
    
    if command_code in commands:
        return commands[command_code][0 if is_request else 1]
    
    return f"Unknown-{command_code}"


# ============================================================================
# Convenience Functions for PyHSS Integration
# ============================================================================

class SWxIntegration:
    """
    Helper class for SWx integration with PyHSS.
    
    This provides a clean interface for the main PyHSS services to
    interact with SWx functionality.
    """
    
    def __init__(self, swx_handler):
        """
        Initialize SWx integration helper.
        
        Args:
            swx_handler: SWxHandler instance
        """
        self.handler = swx_handler
        self.enabled = swx_handler.enabled if swx_handler else False
    
    def process_message(self, packet_vars, avps):
        """
        Process an SWx diameter message.
        
        Args:
            packet_vars: Decoded packet variables
            avps: Decoded AVPs
            
        Returns:
            Response packet or None
        """
        if not self.enabled:
            return None
        
        from services.hss_swx_handler import process_swx_request
        return process_swx_request(self.handler, packet_vars, avps)
    
    def deregister_subscriber(self, imsi, reason_code=0, reason_info=None):
        """
        Deregister subscriber from non-3GPP access.
        
        Args:
            imsi: Subscriber IMSI
            reason_code: Deregistration reason
            reason_info: Optional reason text
            
        Returns:
            Tuple of (success, message)
        """
        if not self.enabled:
            return False, "SWx not enabled"
        
        return self.handler.send_rtr(imsi, reason_code, reason_info)
    
    def push_profile(self, imsi):
        """
        Push updated profile to AAA.
        
        Args:
            imsi: Subscriber IMSI
            
        Returns:
            Tuple of (success, message)
        """
        if not self.enabled:
            return False, "SWx not enabled"
        
        return self.handler.send_ppr(imsi)
    
    def get_registration(self, imsi):
        """
        Get current SWx registration for subscriber.
        
        Args:
            imsi: Subscriber IMSI
            
        Returns:
            Registration dict or None
        """
        if not self.enabled:
            return None
        
        from lib.models_swx import get_swx_registration
        
        try:
            with self.handler.database.get_session() as session:
                reg = get_swx_registration(session, imsi=imsi, active_only=True)
                return reg.to_dict() if reg else None
        except:
            return None


# ============================================================================
# Module initialization
# ============================================================================

swx_init_logger.info(f"{SWX_ADDON_NAME} v{SWX_ADDON_VERSION} module loaded")
