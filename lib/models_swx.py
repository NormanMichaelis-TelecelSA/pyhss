"""
PyHSS SWx Database Models
Database models for SWx interface - non-3GPP access registration and subscription

These models extend the PyHSS database schema to support:
- SWx registration tracking (AAA server assignments)
- Non-3GPP subscription data
- Emergency services configuration

Author: PyHSS Community
License: AGPL-3.0
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

# Import base from PyHSS - this will be configured during integration
# from database import Base
# For standalone development, we create our own Base
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()


class SWX_REGISTRATION(Base):
    """
    Tracks non-3GPP access registrations via SWx interface.
    
    When a subscriber authenticates via WiFi/ePDG, the AAA server sends
    a SAR to register with the HSS. This table tracks those registrations
    for de-registration (RTR) and profile push (PPR) purposes.
    """
    __tablename__ = 'swx_registration'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to subscriber
    subscriber_id = Column(Integer, ForeignKey('subscriber.subscriber_id'), nullable=False, index=True)
    imsi = Column(String(15), nullable=False, index=True)
    
    # AAA Server information (from SAR Origin-Host/Realm)
    aaa_server_name = Column(String(255), nullable=False)  # Origin-Host of AAA
    aaa_realm = Column(String(255), nullable=False)        # Origin-Realm of AAA
    aaa_peer = Column(String(255), nullable=True)          # Diameter peer identifier
    
    # Registration details
    registration_time = Column(DateTime, default=func.now(), nullable=False)
    last_update_time = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Access type information
    access_type = Column(String(50), default='UNTRUSTED_WLAN')  # WLAN, TRUSTED_WLAN, UNTRUSTED_WLAN
    rat_type = Column(String(20), nullable=True)  # WLAN, Virtual, etc.
    
    # PGW/ePDG information
    pgw_address = Column(String(50), nullable=True)  # Serving P-GW address
    epdg_address = Column(String(50), nullable=True)  # ePDG address
    
    # Session information
    session_id = Column(String(255), nullable=True)  # Diameter Session-ID
    
    # State tracking
    is_active = Column(Boolean, default=True, nullable=False)
    deregistration_reason = Column(Integer, nullable=True)  # Reason code if deregistered
    
    # Emergency services
    emergency_services_enabled = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<SWX_REGISTRATION(imsi={self.imsi}, aaa={self.aaa_server_name}, active={self.is_active})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'subscriber_id': self.subscriber_id,
            'imsi': self.imsi,
            'aaa_server_name': self.aaa_server_name,
            'aaa_realm': self.aaa_realm,
            'aaa_peer': self.aaa_peer,
            'registration_time': self.registration_time.isoformat() if self.registration_time else None,
            'last_update_time': self.last_update_time.isoformat() if self.last_update_time else None,
            'access_type': self.access_type,
            'rat_type': self.rat_type,
            'pgw_address': self.pgw_address,
            'epdg_address': self.epdg_address,
            'session_id': self.session_id,
            'is_active': self.is_active,
            'deregistration_reason': self.deregistration_reason,
            'emergency_services_enabled': self.emergency_services_enabled
        }


class NON_3GPP_SUBSCRIPTION(Base):
    """
    Stores non-3GPP specific subscription data for a subscriber.
    
    This extends the normal subscriber subscription with settings specific
    to non-3GPP access (WiFi calling, trusted/untrusted WLAN access).
    """
    __tablename__ = 'non_3gpp_subscription'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to subscriber
    subscriber_id = Column(Integer, ForeignKey('subscriber.subscriber_id'), nullable=False, unique=True, index=True)
    
    # Non-3GPP IP Access authorization
    # 0 = NON_3GPP_SUBSCRIPTION_ALLOWED
    # 1 = NON_3GPP_SUBSCRIPTION_BARRED
    non_3gpp_ip_access = Column(Integer, default=0, nullable=False)
    
    # Non-3GPP IP Access APN
    # 0 = NON_3GPP_APNS_ENABLE (all APNs allowed)
    # 1 = NON_3GPP_APNS_DISABLE (no APNs allowed via non-3GPP)
    non_3gpp_ip_access_apn = Column(Integer, default=0, nullable=False)
    
    # Access Network Trust setting
    # 0 = TRUSTED
    # 1 = UNTRUSTED (default for ePDG/VoWiFi)
    an_trusted = Column(Integer, default=1, nullable=False)
    
    # Aggregate Maximum Bitrate for non-3GPP access
    max_requested_bandwidth_ul = Column(BigInteger, default=100000000)  # 100 Mbps default
    max_requested_bandwidth_dl = Column(BigInteger, default=100000000)  # 100 Mbps default
    
    # Authentication scheme preference
    # EAP-AKA, EAP-AKA', or both
    auth_scheme = Column(String(50), default='EAP-AKA')
    
    # Number of auth vectors to generate
    num_auth_vectors = Column(Integer, default=1)
    
    # Allowed APNs for non-3GPP access (comma-separated list, or empty for all)
    allowed_apns = Column(Text, nullable=True)
    
    # Default APN for non-3GPP access
    default_apn = Column(String(100), default='ims')
    
    # Emergency services
    emergency_services_allowed = Column(Boolean, default=True)
    emergency_apn = Column(String(100), default='sos')
    
    # WLAN offload settings
    wlan_offload_enabled = Column(Boolean, default=True)
    
    # Subscription active flag
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<NON_3GPP_SUBSCRIPTION(subscriber_id={self.subscriber_id}, active={self.is_active})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'subscriber_id': self.subscriber_id,
            'non_3gpp_ip_access': self.non_3gpp_ip_access,
            'non_3gpp_ip_access_apn': self.non_3gpp_ip_access_apn,
            'an_trusted': self.an_trusted,
            'max_requested_bandwidth_ul': self.max_requested_bandwidth_ul,
            'max_requested_bandwidth_dl': self.max_requested_bandwidth_dl,
            'auth_scheme': self.auth_scheme,
            'num_auth_vectors': self.num_auth_vectors,
            'allowed_apns': self.allowed_apns,
            'default_apn': self.default_apn,
            'emergency_services_allowed': self.emergency_services_allowed,
            'emergency_apn': self.emergency_apn,
            'wlan_offload_enabled': self.wlan_offload_enabled,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_allowed_apn_list(self):
        """Return list of allowed APNs."""
        if not self.allowed_apns:
            return []
        return [apn.strip() for apn in self.allowed_apns.split(',') if apn.strip()]


class SWX_APN_CONFIGURATION(Base):
    """
    APN-specific configuration for non-3GPP access.
    
    This allows different APN settings for non-3GPP access vs 3GPP access,
    including different QoS profiles, PGW allocations, etc.
    """
    __tablename__ = 'swx_apn_configuration'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to non-3GPP subscription
    non_3gpp_subscription_id = Column(Integer, ForeignKey('non_3gpp_subscription.id'), nullable=False, index=True)
    
    # Context identifier (unique within subscription)
    context_identifier = Column(Integer, default=1, nullable=False)
    
    # APN name
    apn = Column(String(100), nullable=False)
    
    # PDN Type: 0=IPv4, 1=IPv6, 2=IPv4v6
    pdn_type = Column(Integer, default=0, nullable=False)
    
    # VPLMN Dynamic Address Allowed
    vplmn_dynamic_address_allowed = Column(Integer, default=1)
    
    # QoS settings
    qos_class_identifier = Column(Integer, default=9)  # QCI 9 = default best effort
    priority_level = Column(Integer, default=8)
    preemption_capability = Column(Integer, default=1)  # 0=enabled, 1=disabled
    preemption_vulnerability = Column(Integer, default=0)  # 0=not vulnerable, 1=vulnerable
    
    # APN-level AMBR
    max_requested_bandwidth_ul = Column(BigInteger, default=50000000)  # 50 Mbps
    max_requested_bandwidth_dl = Column(BigInteger, default=100000000)  # 100 Mbps
    
    # PGW allocation
    # 0 = STATIC (use specific PGW)
    # 1 = DYNAMIC (let network choose)
    pgw_allocation_type = Column(Integer, default=1)
    pgw_address = Column(String(50), nullable=True)  # For static allocation
    
    # Active flag
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<SWX_APN_CONFIGURATION(apn={self.apn}, pdn_type={self.pdn_type})>"
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'non_3gpp_subscription_id': self.non_3gpp_subscription_id,
            'context_identifier': self.context_identifier,
            'apn': self.apn,
            'pdn_type': self.pdn_type,
            'vplmn_dynamic_address_allowed': self.vplmn_dynamic_address_allowed,
            'qos_class_identifier': self.qos_class_identifier,
            'priority_level': self.priority_level,
            'preemption_capability': self.preemption_capability,
            'preemption_vulnerability': self.preemption_vulnerability,
            'max_requested_bandwidth_ul': self.max_requested_bandwidth_ul,
            'max_requested_bandwidth_dl': self.max_requested_bandwidth_dl,
            'pgw_allocation_type': self.pgw_allocation_type,
            'pgw_address': self.pgw_address,
            'is_active': self.is_active
        }
    
    def to_apn_config_dict(self):
        """Convert to format expected by diameter_swx.generate_apn_configuration()."""
        return {
            'context_identifier': self.context_identifier,
            'apn': self.apn,
            'pdn_type': self.pdn_type,
            'vplmn_dynamic_address_allowed': self.vplmn_dynamic_address_allowed,
            'max_ul': self.max_requested_bandwidth_ul,
            'max_dl': self.max_requested_bandwidth_dl,
            'qos_profile': {
                'qci': self.qos_class_identifier,
                'priority_level': self.priority_level,
                'preemption_capability': self.preemption_capability,
                'preemption_vulnerability': self.preemption_vulnerability
            }
        }


class SWX_EMERGENCY_INFO(Base):
    """
    Emergency services configuration for non-3GPP access.
    
    Stores emergency service information including URNs, LRF addresses,
    and emergency APN configuration.
    """
    __tablename__ = 'swx_emergency_info'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to subscriber (optional - can be global defaults)
    subscriber_id = Column(Integer, ForeignKey('subscriber.subscriber_id'), nullable=True, index=True)
    
    # Emergency services type
    # 0 = No emergency services
    # 1 = Emergency services supported  
    # 2 = Emergency services and location supported
    emergency_services_type = Column(Integer, default=1)
    
    # Emergency APN
    emergency_apn = Column(String(100), default='sos')
    
    # Location Retrieval Function (LRF) address
    lrf_address = Column(String(255), nullable=True)
    
    # Emergency number list (JSON format)
    emergency_numbers = Column(Text, nullable=True)  # e.g., '["112","911","999"]'
    
    # IMS emergency registration
    ims_voice_over_ps_sessions_supported = Column(Boolean, default=True)
    
    # Emergency PDN type
    emergency_pdn_type = Column(Integer, default=0)  # 0=IPv4, 1=IPv6, 2=IPv4v6
    
    # Active flag
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<SWX_EMERGENCY_INFO(subscriber_id={self.subscriber_id}, type={self.emergency_services_type})>"
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'subscriber_id': self.subscriber_id,
            'emergency_services_type': self.emergency_services_type,
            'emergency_apn': self.emergency_apn,
            'lrf_address': self.lrf_address,
            'emergency_numbers': self.emergency_numbers,
            'ims_voice_over_ps_sessions_supported': self.ims_voice_over_ps_sessions_supported,
            'emergency_pdn_type': self.emergency_pdn_type,
            'is_active': self.is_active
        }


# ============================================================================
# Database helper functions for integration with PyHSS database.py
# ============================================================================

def get_swx_registration(session, imsi=None, subscriber_id=None, active_only=True):
    """
    Get SWx registration for a subscriber.
    
    Args:
        session: SQLAlchemy session
        imsi: Subscriber IMSI (optional)
        subscriber_id: Subscriber ID (optional)
        active_only: Only return active registrations
        
    Returns:
        SWX_REGISTRATION object or None
    """
    query = session.query(SWX_REGISTRATION)
    
    if imsi:
        query = query.filter(SWX_REGISTRATION.imsi == imsi)
    elif subscriber_id:
        query = query.filter(SWX_REGISTRATION.subscriber_id == subscriber_id)
    else:
        return None
    
    if active_only:
        query = query.filter(SWX_REGISTRATION.is_active == True)
    
    return query.first()


def create_or_update_swx_registration(session, imsi, subscriber_id, aaa_server_name, 
                                       aaa_realm, aaa_peer=None, access_type='UNTRUSTED_WLAN',
                                       session_id=None):
    """
    Create or update SWx registration.
    
    Args:
        session: SQLAlchemy session
        imsi: Subscriber IMSI
        subscriber_id: Subscriber ID
        aaa_server_name: AAA server Origin-Host
        aaa_realm: AAA server Origin-Realm
        aaa_peer: Diameter peer identifier
        access_type: Access type (WLAN, TRUSTED_WLAN, UNTRUSTED_WLAN)
        session_id: Diameter session ID
        
    Returns:
        SWX_REGISTRATION object
    """
    registration = get_swx_registration(session, imsi=imsi)
    
    if registration:
        # Update existing registration
        registration.aaa_server_name = aaa_server_name
        registration.aaa_realm = aaa_realm
        registration.aaa_peer = aaa_peer
        registration.access_type = access_type
        registration.session_id = session_id
        registration.is_active = True
        registration.deregistration_reason = None
    else:
        # Create new registration
        registration = SWX_REGISTRATION(
            subscriber_id=subscriber_id,
            imsi=imsi,
            aaa_server_name=aaa_server_name,
            aaa_realm=aaa_realm,
            aaa_peer=aaa_peer,
            access_type=access_type,
            session_id=session_id,
            is_active=True
        )
        session.add(registration)
    
    session.commit()
    return registration


def deregister_swx(session, imsi, reason_code=0):
    """
    Mark SWx registration as inactive (deregistered).
    
    Args:
        session: SQLAlchemy session
        imsi: Subscriber IMSI
        reason_code: Deregistration reason code
        
    Returns:
        True if deregistered, False if no registration found
    """
    registration = get_swx_registration(session, imsi=imsi, active_only=True)
    
    if registration:
        registration.is_active = False
        registration.deregistration_reason = reason_code
        session.commit()
        return True
    
    return False


def get_non_3gpp_subscription(session, subscriber_id):
    """
    Get non-3GPP subscription for a subscriber.
    
    Args:
        session: SQLAlchemy session
        subscriber_id: Subscriber ID
        
    Returns:
        NON_3GPP_SUBSCRIPTION object or None
    """
    return session.query(NON_3GPP_SUBSCRIPTION).filter(
        NON_3GPP_SUBSCRIPTION.subscriber_id == subscriber_id,
        NON_3GPP_SUBSCRIPTION.is_active == True
    ).first()


def get_swx_apn_configurations(session, non_3gpp_subscription_id):
    """
    Get APN configurations for non-3GPP subscription.
    
    Args:
        session: SQLAlchemy session
        non_3gpp_subscription_id: Non-3GPP subscription ID
        
    Returns:
        List of SWX_APN_CONFIGURATION objects
    """
    return session.query(SWX_APN_CONFIGURATION).filter(
        SWX_APN_CONFIGURATION.non_3gpp_subscription_id == non_3gpp_subscription_id,
        SWX_APN_CONFIGURATION.is_active == True
    ).all()


def create_default_non_3gpp_subscription(session, subscriber_id, default_apn='ims'):
    """
    Create default non-3GPP subscription for a subscriber.
    
    Args:
        session: SQLAlchemy session
        subscriber_id: Subscriber ID
        default_apn: Default APN name
        
    Returns:
        NON_3GPP_SUBSCRIPTION object
    """
    subscription = NON_3GPP_SUBSCRIPTION(
        subscriber_id=subscriber_id,
        non_3gpp_ip_access=0,  # Allowed
        non_3gpp_ip_access_apn=0,  # All APNs enabled
        an_trusted=1,  # Untrusted (ePDG)
        default_apn=default_apn,
        is_active=True
    )
    session.add(subscription)
    session.commit()
    
    # Create default APN configuration
    apn_config = SWX_APN_CONFIGURATION(
        non_3gpp_subscription_id=subscription.id,
        context_identifier=1,
        apn=default_apn,
        pdn_type=0,  # IPv4
        is_active=True
    )
    session.add(apn_config)
    session.commit()
    
    return subscription
