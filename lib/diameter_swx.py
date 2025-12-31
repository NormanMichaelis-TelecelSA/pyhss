"""
PyHSS SWx Interface Implementation
3GPP TS 29.273 - Diameter SWx Interface for non-3GPP access (WiFi Calling)

This module provides SWx Diameter interface support for PyHSS, enabling
authentication and authorization of subscribers accessing via non-3GPP
networks (e.g., WiFi calling with osmo-epdg).

Application ID: 16777265 (3GPP SWx)
Vendor ID: 10415 (3GPP)

Supported Commands:
- MAR/MAA (303) - Multimedia-Auth-Request/Answer
- SAR/SAA (301) - Server-Assignment-Request/Answer  
- RTR/RTA (304) - Registration-Termination-Request/Answer
- PPR/PPA (305) - Push-Profile-Request/Answer

Author: PyHSS Community
License: AGPL-3.0
"""

import binascii
import logging
import os
import sys
import time
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.DEBUG)
swx_logger = logging.getLogger('SWxLogger')

# SWx Constants
SWX_APPLICATION_ID = 16777265      # 3GPP SWx Application ID
VENDOR_ID_3GPP = 10415             # 3GPP Vendor ID

# SWx Command Codes (from TS 29.229)
SWX_CMD_MAR = 303  # Multimedia-Auth-Request/Answer
SWX_CMD_SAR = 301  # Server-Assignment-Request/Answer
SWX_CMD_RTR = 304  # Registration-Termination-Request/Answer
SWX_CMD_PPR = 305  # Push-Profile-Request/Answer

# SWx AVP Codes (Vendor-Specific 3GPP)
AVP_SIP_AUTH_DATA_ITEM = 612         # Grouped AVP for auth data
AVP_SIP_ITEM_NUMBER = 613            # Item number in auth data
AVP_SIP_AUTHENTICATE = 609           # RAND || AUTN (challenge)
AVP_SIP_AUTHORIZATION = 610          # XRES (expected response)
AVP_SIP_AUTHENTICATION_SCHEME = 608  # Auth scheme (EAP-AKA, EAP-AKA')
AVP_SIP_NUMBER_AUTH_ITEMS = 607      # Number of auth items
AVP_CONFIDENTIALITY_KEY = 625        # CK
AVP_INTEGRITY_KEY = 626              # IK

# Server Assignment Type values (TS 29.229)
AVP_SERVER_ASSIGNMENT_TYPE = 614
SERVER_ASSIGNMENT_NO_ASSIGNMENT = 0
SERVER_ASSIGNMENT_REGISTRATION = 1
SERVER_ASSIGNMENT_RE_REGISTRATION = 2
SERVER_ASSIGNMENT_UNREGISTERED_USER = 3
SERVER_ASSIGNMENT_TIMEOUT_DEREGISTRATION = 4
SERVER_ASSIGNMENT_USER_DEREGISTRATION = 5
SERVER_ASSIGNMENT_DEREGISTRATION_STORE = 6
SERVER_ASSIGNMENT_USER_DEREGISTRATION_STORE = 7
SERVER_ASSIGNMENT_ADMINISTRATIVE_DEREGISTRATION = 8
SERVER_ASSIGNMENT_AUTHENTICATION_FAILURE = 9
SERVER_ASSIGNMENT_AUTHENTICATION_TIMEOUT = 10
SERVER_ASSIGNMENT_DEREGISTRATION_TOO_MUCH_DATA = 11
SERVER_ASSIGNMENT_AAA_USER_DATA_REQUEST = 12
SERVER_ASSIGNMENT_PGW_UPDATE = 13
SERVER_ASSIGNMENT_RESTORATION = 14

# Non-3GPP User Data AVPs
AVP_NON_3GPP_USER_DATA = 1500        # Grouped - contains subscription data
AVP_NON_3GPP_IP_ACCESS = 1501        # Access type
AVP_NON_3GPP_IP_ACCESS_APN = 1502    # Access APN setting
AVP_AN_TRUSTED = 1503                # Trusted/Untrusted indicator
AVP_CONTEXT_IDENTIFIER = 1423        # Context ID for APN config
AVP_APN_CONFIGURATION = 1430         # APN Configuration grouped AVP
AVP_SUBSCRIBED_PERIODIC_RAU_TAU_TIMER = 1619  # Timer value
AVP_MIP6_FEATURE_VECTOR = 124        # MIPv6 feature bits

# APN Configuration AVPs  
AVP_SERVICE_SELECTION = 493          # APN name
AVP_PDN_TYPE = 1456                  # IPv4, IPv6, IPv4v6
AVP_AMBR = 1435                      # Aggregate Max Bitrate
AVP_QOS_PROFILE_TEMPLATE = 1463      # QoS template
AVP_EPS_SUBSCRIBED_QOS_PROFILE = 1431  # EPS QoS profile
AVP_VPLMN_DYNAMIC_ADDRESS_ALLOWED = 1432  # Dynamic addr allowed
AVP_PDN_GW_ALLOCATION_TYPE = 1438    # Static/Dynamic PGW

# Deregistration Reason AVP
AVP_DEREGISTRATION_REASON = 615      # Grouped
AVP_REASON_CODE = 616                # Reason enum
AVP_REASON_INFO = 617                # Reason text

# Reason Code values
REASON_PERMANENT_TERMINATION = 0
REASON_NEW_SERVER_ASSIGNED = 1
REASON_SERVER_CHANGE = 2
REASON_REMOVE_SCSCF = 3

# Result Codes (TS 29.229 section 6.2)
DIAMETER_SUCCESS = 2001
DIAMETER_FIRST_REGISTRATION = 2001
DIAMETER_SUBSEQUENT_REGISTRATION = 2001
DIAMETER_ERROR_USER_UNKNOWN = 5001
DIAMETER_ERROR_IDENTITIES_DONT_MATCH = 5002
DIAMETER_ERROR_IDENTITY_NOT_REGISTERED = 5003
DIAMETER_ERROR_ROAMING_NOT_ALLOWED = 5004
DIAMETER_ERROR_IDENTITY_ALREADY_REGISTERED = 5005
DIAMETER_ERROR_AUTH_SCHEME_NOT_SUPPORTED = 5006
DIAMETER_ERROR_IN_ASSIGNMENT_TYPE = 5007
DIAMETER_ERROR_TOO_MUCH_DATA = 5008
DIAMETER_ERROR_NOT_SUPPORTED_USER_DATA = 5009
DIAMETER_ERROR_FEATURE_UNSUPPORTED = 5011
DIAMETER_ERROR_USER_DATA_NOT_AVAILABLE = 5032
DIAMETER_ERROR_USER_NO_APN_SUBSCRIPTION = 5451


class DiameterSWx:
    """
    SWx Diameter Interface handler for PyHSS.
    
    This class extends the base PyHSS Diameter class with SWx-specific
    message encoding/decoding capabilities for non-3GPP access authentication.
    """
    
    def __init__(self, parent_diameter):
        """
        Initialize SWx handler with reference to parent Diameter instance.
        
        Args:
            parent_diameter: Reference to the main Diameter class instance
        """
        self.diameter = parent_diameter
        self.OriginHost = parent_diameter.OriginHost
        self.OriginRealm = parent_diameter.OriginRealm
        self.ProductName = parent_diameter.ProductName
        self.MCC = parent_diameter.MCC
        self.MNC = parent_diameter.MNC
        swx_logger.info(f"SWx Interface initialized for {self.OriginHost}@{self.OriginRealm}")
    
    def int_to_hex(self, value, length):
        """Convert integer to hex string with specified byte length."""
        return format(value, 'x').zfill(length * 2)
    
    def generate_avp(self, avp_code, avp_flags, avp_content):
        """Wrapper to parent's generate_avp."""
        return self.diameter.generate_avp(avp_code, avp_flags, avp_content)
    
    def generate_vendor_avp(self, avp_code, avp_flags, avp_vendorid, avp_content):
        """Wrapper to parent's generate_vendor_avp."""
        return self.diameter.generate_vendor_avp(avp_code, avp_flags, avp_vendorid, avp_content)
    
    def generate_diameter_packet(self, version, flags, cmd_code, app_id, hop_by_hop, end_to_end, avp):
        """Wrapper to parent's generate_diameter_packet."""
        return self.diameter.generate_diameter_packet(version, flags, cmd_code, app_id, hop_by_hop, end_to_end, avp)

    def get_avp_data(self, avps, avp_code):
        """Wrapper to parent's get_avp_data."""
        return self.diameter.get_avp_data(avps, avp_code)

    # =========================================================================
    # SWx SIP-Auth-Data-Item AVP Generation
    # =========================================================================
    
    def generate_sip_auth_data_item(self, rand, autn, xres, ck, ik, auth_scheme="EAP-AKA"):
        """
        Generate SIP-Auth-Data-Item grouped AVP for SWx MAA response.
        
        This AVP contains the EAP-AKA/AKA' authentication vectors needed
        for non-3GPP access authentication.
        
        Args:
            rand: 16-byte RAND value (hex string)
            autn: 16-byte AUTN value (hex string)  
            xres: 4-16 byte XRES value (hex string)
            ck: 16-byte Confidentiality Key (hex string)
            ik: 16-byte Integrity Key (hex string)
            auth_scheme: Authentication scheme ("EAP-AKA" or "EAP-AKA'")
            
        Returns:
            Hex string containing the SIP-Auth-Data-Item grouped AVP
        """
        swx_logger.debug(f"Generating SIP-Auth-Data-Item with scheme {auth_scheme}")
        
        avp_content = ""
        
        # SIP-Item-Number AVP (613) - usually 1 for single vector
        avp_content += self.generate_vendor_avp(
            AVP_SIP_ITEM_NUMBER, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(1, 4)
        )
        
        # SIP-Authentication-Scheme AVP (608)
        scheme_hex = str(binascii.hexlify(auth_scheme.encode('utf-8')), 'ascii')
        avp_content += self.generate_vendor_avp(
            AVP_SIP_AUTHENTICATION_SCHEME, "c0", VENDOR_ID_3GPP,
            scheme_hex
        )
        
        # SIP-Authenticate AVP (609) - Contains RAND || AUTN
        # RAND (16 bytes) + AUTN (16 bytes) = 32 bytes
        sip_authenticate = rand + autn
        avp_content += self.generate_vendor_avp(
            AVP_SIP_AUTHENTICATE, "c0", VENDOR_ID_3GPP,
            sip_authenticate
        )
        
        # SIP-Authorization AVP (610) - Contains XRES
        avp_content += self.generate_vendor_avp(
            AVP_SIP_AUTHORIZATION, "c0", VENDOR_ID_3GPP,
            xres
        )
        
        # Confidentiality-Key AVP (625)
        avp_content += self.generate_vendor_avp(
            AVP_CONFIDENTIALITY_KEY, "c0", VENDOR_ID_3GPP,
            ck
        )
        
        # Integrity-Key AVP (626)
        avp_content += self.generate_vendor_avp(
            AVP_INTEGRITY_KEY, "c0", VENDOR_ID_3GPP,
            ik
        )
        
        # Wrap in SIP-Auth-Data-Item grouped AVP (612)
        sip_auth_data_item = self.generate_vendor_avp(
            AVP_SIP_AUTH_DATA_ITEM, "c0", VENDOR_ID_3GPP,
            avp_content
        )
        
        return sip_auth_data_item
    
    # =========================================================================
    # Non-3GPP User Data AVP Generation  
    # =========================================================================
    
    def generate_non_3gpp_user_data(self, subscriber_data, apn_configs):
        """
        Generate Non-3GPP-User-Data grouped AVP for SAA response.
        
        This AVP contains the subscriber profile and APN configurations
        for non-3GPP access.
        
        Args:
            subscriber_data: Dict with subscriber subscription info
            apn_configs: List of APN configuration dicts
            
        Returns:
            Hex string containing Non-3GPP-User-Data grouped AVP
        """
        swx_logger.debug("Generating Non-3GPP-User-Data AVP")
        
        avp_content = ""
        
        # Non-3GPP-IP-Access AVP (1501) - Access type allowed
        # 0 = Non_3GPP_SUBSCRIPTION_ALLOWED
        non_3gpp_ip_access = subscriber_data.get('non_3gpp_ip_access', 0)
        avp_content += self.generate_vendor_avp(
            AVP_NON_3GPP_IP_ACCESS, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(non_3gpp_ip_access, 4)
        )
        
        # Non-3GPP-IP-Access-APN AVP (1502)
        # 0 = Non_3GPP_APNS_ENABLE
        non_3gpp_ip_access_apn = subscriber_data.get('non_3gpp_ip_access_apn', 0)
        avp_content += self.generate_vendor_avp(
            AVP_NON_3GPP_IP_ACCESS_APN, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(non_3gpp_ip_access_apn, 4)
        )
        
        # AN-Trusted AVP (1503) - Trusted access network indicator
        # 0 = TRUSTED, 1 = UNTRUSTED
        an_trusted = subscriber_data.get('an_trusted', 1)  # Default untrusted for ePDG
        avp_content += self.generate_vendor_avp(
            AVP_AN_TRUSTED, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(an_trusted, 4)
        )
        
        # Add AMBR if present
        if 'max_dl' in subscriber_data and 'max_ul' in subscriber_data:
            ambr_content = ""
            # Max-Requested-Bandwidth-UL (516)
            ambr_content += self.generate_vendor_avp(
                516, "c0", VENDOR_ID_3GPP,
                self.int_to_hex(subscriber_data['max_ul'], 4)
            )
            # Max-Requested-Bandwidth-DL (515)
            ambr_content += self.generate_vendor_avp(
                515, "c0", VENDOR_ID_3GPP,
                self.int_to_hex(subscriber_data['max_dl'], 4)
            )
            avp_content += self.generate_vendor_avp(
                AVP_AMBR, "c0", VENDOR_ID_3GPP,
                ambr_content
            )
        
        # Add APN configurations
        for apn_config in apn_configs:
            avp_content += self.generate_apn_configuration(apn_config)
        
        # Wrap in Non-3GPP-User-Data grouped AVP (1500)
        non_3gpp_user_data = self.generate_vendor_avp(
            AVP_NON_3GPP_USER_DATA, "c0", VENDOR_ID_3GPP,
            avp_content
        )
        
        return non_3gpp_user_data
    
    def generate_apn_configuration(self, apn_config):
        """
        Generate APN-Configuration grouped AVP.
        
        Args:
            apn_config: Dict with APN configuration data
            
        Returns:
            Hex string containing APN-Configuration grouped AVP
        """
        avp_content = ""
        
        # Context-Identifier (1423)
        context_id = apn_config.get('context_identifier', 1)
        avp_content += self.generate_vendor_avp(
            AVP_CONTEXT_IDENTIFIER, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(context_id, 4)
        )
        
        # Service-Selection (493) - APN Name
        apn_name = apn_config.get('apn', 'ims')
        apn_hex = str(binascii.hexlify(apn_name.encode('utf-8')), 'ascii')
        avp_content += self.generate_avp(AVP_SERVICE_SELECTION, "40", apn_hex)
        
        # PDN-Type (1456) - IPv4=0, IPv6=1, IPv4v6=2
        pdn_type = apn_config.get('pdn_type', 0)
        avp_content += self.generate_vendor_avp(
            AVP_PDN_TYPE, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(pdn_type, 4)
        )
        
        # VPLMN-Dynamic-Address-Allowed (1432)
        vplmn_dynamic = apn_config.get('vplmn_dynamic_address_allowed', 1)
        avp_content += self.generate_vendor_avp(
            AVP_VPLMN_DYNAMIC_ADDRESS_ALLOWED, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(vplmn_dynamic, 4)
        )
        
        # EPS-Subscribed-QoS-Profile (1431) if present
        if 'qos_profile' in apn_config:
            qos_content = self._generate_qos_profile(apn_config['qos_profile'])
            avp_content += self.generate_vendor_avp(
                AVP_EPS_SUBSCRIBED_QOS_PROFILE, "c0", VENDOR_ID_3GPP,
                qos_content
            )
        
        # AMBR for this APN
        if 'max_dl' in apn_config and 'max_ul' in apn_config:
            ambr_content = ""
            ambr_content += self.generate_vendor_avp(
                516, "c0", VENDOR_ID_3GPP,
                self.int_to_hex(apn_config['max_ul'], 4)
            )
            ambr_content += self.generate_vendor_avp(
                515, "c0", VENDOR_ID_3GPP,
                self.int_to_hex(apn_config['max_dl'], 4)
            )
            avp_content += self.generate_vendor_avp(
                AVP_AMBR, "c0", VENDOR_ID_3GPP,
                ambr_content
            )
        
        # Wrap in APN-Configuration (1430)
        apn_configuration = self.generate_vendor_avp(
            AVP_APN_CONFIGURATION, "c0", VENDOR_ID_3GPP,
            avp_content
        )
        
        return apn_configuration
    
    def _generate_qos_profile(self, qos_profile):
        """Generate EPS-Subscribed-QoS-Profile content."""
        content = ""
        
        # QoS-Class-Identifier (1028)
        qci = qos_profile.get('qci', 9)  # Default QCI 9 for best effort
        content += self.generate_vendor_avp(
            1028, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(qci, 4)
        )
        
        # Allocation-Retention-Priority (1034) grouped
        arp_content = ""
        # Priority-Level (1046)
        priority = qos_profile.get('priority_level', 8)
        arp_content += self.generate_vendor_avp(
            1046, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(priority, 4)
        )
        # Pre-emption-Capability (1047)
        preempt_cap = qos_profile.get('preemption_capability', 1)
        arp_content += self.generate_vendor_avp(
            1047, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(preempt_cap, 4)
        )
        # Pre-emption-Vulnerability (1048)
        preempt_vuln = qos_profile.get('preemption_vulnerability', 0)
        arp_content += self.generate_vendor_avp(
            1048, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(preempt_vuln, 4)
        )
        content += self.generate_vendor_avp(1034, "c0", VENDOR_ID_3GPP, arp_content)
        
        return content

    # =========================================================================
    # SWx Multimedia-Auth-Answer (MAA) - Command Code 303
    # =========================================================================
    
    def Answer_16777265_303(self, packet_vars, avps, subscriber_data, auth_vectors):
        """
        Generate Multimedia-Auth-Answer (MAA) for SWx interface.
        
        This is sent in response to a MAR from the 3GPP AAA server (osmo-epdg)
        and contains the EAP-AKA authentication vectors.
        
        Args:
            packet_vars: Decoded packet variables from request
            avps: List of decoded AVPs from request
            subscriber_data: Dict with subscriber info from database
            auth_vectors: List of dicts with auth vector data:
                         [{'rand': '...', 'autn': '...', 'xres': '...', 
                           'ck': '...', 'ik': '...'}]
        
        Returns:
            Tuple of (response_hex, result_code)
        """
        swx_logger.info("Generating SWx Multimedia-Auth-Answer (MAA)")
        
        avp = ""
        
        # Session-ID from request
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        # Vendor-Specific-Application-Id
        vendor_avp = self.generate_vendor_avp(266, "c0", VENDOR_ID_3GPP, "")
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        vendor_avp_content += self.generate_vendor_avp(266, "c0", VENDOR_ID_3GPP, 
                                                        self.int_to_hex(VENDOR_ID_3GPP, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        # Auth-Session-State (No state maintained)
        avp += self.generate_avp(277, 40, "00000001")
        
        # Origin-Host and Origin-Realm
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        # User-Name (IMSI in NAI format or bare IMSI)
        user_name = self.get_avp_data(avps, 1)[0]
        avp += self.generate_avp(1, 40, user_name)
        
        # Add SIP-Number-Auth-Items with count
        num_vectors = len(auth_vectors)
        avp += self.generate_vendor_avp(
            AVP_SIP_NUMBER_AUTH_ITEMS, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(num_vectors, 4)
        )
        
        # Add each auth vector as SIP-Auth-Data-Item
        auth_scheme = subscriber_data.get('auth_scheme', 'EAP-AKA')
        for vector in auth_vectors:
            avp += self.generate_sip_auth_data_item(
                rand=vector['rand'],
                autn=vector['autn'],
                xres=vector['xres'],
                ck=vector['ck'],
                ik=vector['ik'],
                auth_scheme=auth_scheme
            )
        
        # Result-Code (DIAMETER_SUCCESS)
        avp += self.generate_avp(268, 40, self.int_to_hex(DIAMETER_SUCCESS, 4))
        
        # Generate response packet
        # Flags: 0x40 = response (no request bit)
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_MAR, 
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        swx_logger.info(f"MAA generated with {num_vectors} auth vector(s)")
        return response, DIAMETER_SUCCESS
    
    def Answer_16777265_303_Error(self, packet_vars, avps, error_code):
        """
        Generate error Multimedia-Auth-Answer (MAA).
        
        Args:
            packet_vars: Decoded packet variables
            avps: Decoded AVPs from request
            error_code: Diameter error/experimental result code
        
        Returns:
            Tuple of (response_hex, error_code)
        """
        swx_logger.warning(f"Generating SWx MAA Error response: {error_code}")
        
        avp = ""
        
        # Session-ID
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        # Vendor-Specific-Application-Id
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        # Auth-Session-State
        avp += self.generate_avp(277, 40, "00000001")
        
        # Origin-Host and Origin-Realm
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        # User-Name (required even on error per 3GPP specs)
        user_name = self.get_avp_data(avps, 1)
        if user_name:
            avp += self.generate_avp(1, 40, user_name[0])
        
        # Experimental-Result (for 3GPP error codes)
        if error_code >= 5000:
            exp_result = self.generate_avp(258, 40, self.int_to_hex(VENDOR_ID_3GPP, 4))
            exp_result += self.generate_avp(298, 40, self.int_to_hex(error_code, 4))
            avp += self.generate_avp(297, 40, exp_result)
        else:
            # Standard Result-Code
            avp += self.generate_avp(268, 40, self.int_to_hex(error_code, 4))
        
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_MAR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        return response, error_code

    # =========================================================================
    # SWx Server-Assignment-Answer (SAA) - Command Code 301
    # =========================================================================
    
    def Answer_16777265_301(self, packet_vars, avps, subscriber_data, apn_configs):
        """
        Generate Server-Assignment-Answer (SAA) for SWx interface.
        
        This is sent in response to a SAR from the 3GPP AAA server and contains
        the subscriber profile for non-3GPP access.
        
        Args:
            packet_vars: Decoded packet variables from request
            avps: List of decoded AVPs from request
            subscriber_data: Dict with subscriber subscription data
            apn_configs: List of APN configuration dicts
        
        Returns:
            Tuple of (response_hex, result_code)
        """
        swx_logger.info("Generating SWx Server-Assignment-Answer (SAA)")
        
        avp = ""
        
        # Session-ID
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        # Vendor-Specific-Application-Id
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        vendor_avp_content += self.generate_vendor_avp(266, "c0", VENDOR_ID_3GPP,
                                                        self.int_to_hex(VENDOR_ID_3GPP, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        # Auth-Session-State
        avp += self.generate_avp(277, 40, "00000001")
        
        # Origin-Host and Origin-Realm
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        # User-Name
        user_name = self.get_avp_data(avps, 1)[0]
        avp += self.generate_avp(1, 40, user_name)
        
        # Non-3GPP-User-Data with subscription info
        avp += self.generate_non_3gpp_user_data(subscriber_data, apn_configs)
        
        # Result-Code (DIAMETER_SUCCESS)
        avp += self.generate_avp(268, 40, self.int_to_hex(DIAMETER_SUCCESS, 4))
        
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_SAR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        swx_logger.info("SAA generated with Non-3GPP-User-Data")
        return response, DIAMETER_SUCCESS
    
    def Answer_16777265_301_Error(self, packet_vars, avps, error_code):
        """Generate error Server-Assignment-Answer."""
        swx_logger.warning(f"Generating SWx SAA Error: {error_code}")
        
        avp = ""
        
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        avp += self.generate_avp(277, 40, "00000001")
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        user_name = self.get_avp_data(avps, 1)
        if user_name:
            avp += self.generate_avp(1, 40, user_name[0])
        
        if error_code >= 5000:
            exp_result = self.generate_avp(258, 40, self.int_to_hex(VENDOR_ID_3GPP, 4))
            exp_result += self.generate_avp(298, 40, self.int_to_hex(error_code, 4))
            avp += self.generate_avp(297, 40, exp_result)
        else:
            avp += self.generate_avp(268, 40, self.int_to_hex(error_code, 4))
        
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_SAR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        return response, error_code

    # =========================================================================
    # SWx Registration-Termination-Request (RTR) - Command Code 304
    # =========================================================================
    
    def Request_16777265_304(self, imsi, destination_host, destination_realm, 
                              reason_code=REASON_PERMANENT_TERMINATION, reason_info=None):
        """
        Generate Registration-Termination-Request (RTR) for SWx interface.
        
        This is sent by the HSS to the 3GPP AAA server to de-register a subscriber
        from non-3GPP access.
        
        Args:
            imsi: Subscriber IMSI
            destination_host: AAA server Origin-Host to send to
            destination_realm: AAA server realm
            reason_code: Deregistration reason code
            reason_info: Optional reason information text
        
        Returns:
            Hex string of RTR message
        """
        swx_logger.info(f"Generating SWx RTR for IMSI {imsi}")
        
        avp = ""
        
        # Session-ID
        session_id = f"swx-rtr-{imsi}-{int(time.time())}"
        session_id_hex = str(binascii.hexlify(session_id.encode('utf-8')), 'ascii')
        avp += self.generate_avp(263, 40, session_id_hex)
        
        # Vendor-Specific-Application-Id
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        vendor_avp_content += self.generate_vendor_avp(266, "c0", VENDOR_ID_3GPP,
                                                        self.int_to_hex(VENDOR_ID_3GPP, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        # Auth-Session-State
        avp += self.generate_avp(277, 40, "00000001")
        
        # Origin-Host and Origin-Realm
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        # Destination-Host and Destination-Realm
        dest_host_hex = str(binascii.hexlify(destination_host.encode('utf-8')), 'ascii')
        avp += self.generate_avp(293, 40, dest_host_hex)
        dest_realm_hex = str(binascii.hexlify(destination_realm.encode('utf-8')), 'ascii')
        avp += self.generate_avp(283, 40, dest_realm_hex)
        
        # User-Name (IMSI)
        imsi_hex = str(binascii.hexlify(imsi.encode('utf-8')), 'ascii')
        avp += self.generate_avp(1, 40, imsi_hex)
        
        # Deregistration-Reason (615) grouped AVP
        dereg_content = ""
        # Reason-Code (616)
        dereg_content += self.generate_vendor_avp(
            AVP_REASON_CODE, "c0", VENDOR_ID_3GPP,
            self.int_to_hex(reason_code, 4)
        )
        # Reason-Info (617) - optional
        if reason_info:
            reason_hex = str(binascii.hexlify(reason_info.encode('utf-8')), 'ascii')
            dereg_content += self.generate_vendor_avp(
                AVP_REASON_INFO, "c0", VENDOR_ID_3GPP,
                reason_hex
            )
        avp += self.generate_vendor_avp(
            AVP_DEREGISTRATION_REASON, "c0", VENDOR_ID_3GPP,
            dereg_content
        )
        
        # Generate unique identifiers
        hop_by_hop = format(int(time.time() * 1000) & 0xFFFFFFFF, 'x').zfill(8)
        end_to_end = format((int(time.time()) << 20) & 0xFFFFFFFF, 'x').zfill(8)
        
        # Generate request packet - Flags: 0xC0 = Request + Proxiable
        request = self.generate_diameter_packet(
            "01", "c0", SWX_CMD_RTR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            hop_by_hop, end_to_end, avp
        )
        
        swx_logger.info(f"RTR generated for {imsi} to {destination_host}")
        return request

    def Answer_16777265_304(self, packet_vars, avps):
        """
        Generate Registration-Termination-Answer (RTA).
        
        Sent by AAA to HSS in response to RTR.
        """
        avp = ""
        
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        avp += self.generate_avp(277, 40, "00000001")
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        avp += self.generate_avp(268, 40, self.int_to_hex(DIAMETER_SUCCESS, 4))
        
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_RTR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        return response, DIAMETER_SUCCESS

    # =========================================================================
    # SWx Push-Profile-Request (PPR) - Command Code 305
    # =========================================================================
    
    def Request_16777265_305(self, imsi, destination_host, destination_realm, 
                              subscriber_data, apn_configs=None):
        """
        Generate Push-Profile-Request (PPR) for SWx interface.
        
        This is sent by the HSS to push updated subscriber data to the 3GPP AAA.
        
        Args:
            imsi: Subscriber IMSI
            destination_host: AAA server Origin-Host
            destination_realm: AAA server realm
            subscriber_data: Updated subscriber subscription data
            apn_configs: Optional updated APN configurations
        
        Returns:
            Hex string of PPR message
        """
        swx_logger.info(f"Generating SWx PPR for IMSI {imsi}")
        
        avp = ""
        
        # Session-ID
        session_id = f"swx-ppr-{imsi}-{int(time.time())}"
        session_id_hex = str(binascii.hexlify(session_id.encode('utf-8')), 'ascii')
        avp += self.generate_avp(263, 40, session_id_hex)
        
        # Vendor-Specific-Application-Id
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        vendor_avp_content += self.generate_vendor_avp(266, "c0", VENDOR_ID_3GPP,
                                                        self.int_to_hex(VENDOR_ID_3GPP, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        # Auth-Session-State
        avp += self.generate_avp(277, 40, "00000001")
        
        # Origin-Host and Origin-Realm
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        
        # Destination-Host and Destination-Realm
        dest_host_hex = str(binascii.hexlify(destination_host.encode('utf-8')), 'ascii')
        avp += self.generate_avp(293, 40, dest_host_hex)
        dest_realm_hex = str(binascii.hexlify(destination_realm.encode('utf-8')), 'ascii')
        avp += self.generate_avp(283, 40, dest_realm_hex)
        
        # User-Name (IMSI)
        imsi_hex = str(binascii.hexlify(imsi.encode('utf-8')), 'ascii')
        avp += self.generate_avp(1, 40, imsi_hex)
        
        # Non-3GPP-User-Data with updated subscription
        if apn_configs is None:
            apn_configs = []
        avp += self.generate_non_3gpp_user_data(subscriber_data, apn_configs)
        
        # Generate unique identifiers
        hop_by_hop = format(int(time.time() * 1000) & 0xFFFFFFFF, 'x').zfill(8)
        end_to_end = format((int(time.time()) << 20) & 0xFFFFFFFF, 'x').zfill(8)
        
        request = self.generate_diameter_packet(
            "01", "c0", SWX_CMD_PPR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            hop_by_hop, end_to_end, avp
        )
        
        swx_logger.info(f"PPR generated for {imsi}")
        return request

    def Answer_16777265_305(self, packet_vars, avps):
        """
        Generate Push-Profile-Answer (PPA).
        
        Sent by AAA to HSS in response to PPR.
        """
        avp = ""
        
        session_id = self.get_avp_data(avps, 263)[0]
        avp += self.generate_avp(263, 40, session_id)
        
        vendor_avp_content = self.generate_avp(258, 40, self.int_to_hex(SWX_APPLICATION_ID, 4))
        avp += self.generate_avp(260, 40, vendor_avp_content)
        
        avp += self.generate_avp(277, 40, "00000001")
        avp += self.generate_avp(264, 40, self.OriginHost)
        avp += self.generate_avp(296, 40, self.OriginRealm)
        avp += self.generate_avp(268, 40, self.int_to_hex(DIAMETER_SUCCESS, 4))
        
        response = self.generate_diameter_packet(
            "01", "40", SWX_CMD_PPR,
            self.int_to_hex(SWX_APPLICATION_ID, 4),
            packet_vars['hop-by-hop-identifier'],
            packet_vars['end-to-end-identifier'],
            avp
        )
        
        return response, DIAMETER_SUCCESS

    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def extract_imsi_from_username(self, username_hex):
        """
        Extract IMSI from User-Name AVP value.
        
        The User-Name can be in various formats:
        - Bare IMSI: "001010000000001"
        - NAI format: "0001010000000001@nai.epc.mnc001.mcc001.3gppnetwork.org"
        - Decorated NAI: "wlan!0001010000000001@nai..."
        
        Args:
            username_hex: Hex-encoded User-Name AVP value
            
        Returns:
            Extracted IMSI string (15 digits)
        """
        try:
            username = binascii.unhexlify(username_hex).decode('utf-8')
            swx_logger.debug(f"Extracting IMSI from username: {username}")
            
            # Remove wlan! or similar prefix
            if '!' in username:
                username = username.split('!')[1]
            
            # Remove @domain suffix
            if '@' in username:
                username = username.split('@')[0]
            
            # Remove leading 0 if present (NAI format uses 0<IMSI>)
            if len(username) == 16 and username.startswith('0'):
                username = username[1:]
            
            # Validate IMSI format
            if len(username) == 15 and username.isdigit():
                return username
            else:
                swx_logger.error(f"Invalid IMSI format: {username}")
                return None
                
        except Exception as e:
            swx_logger.error(f"Failed to extract IMSI: {e}")
            return None
    
    def get_server_assignment_type(self, avps):
        """Extract Server-Assignment-Type from SAR."""
        sat_data = self.get_avp_data(avps, AVP_SERVER_ASSIGNMENT_TYPE)
        if sat_data:
            return int(sat_data[0], 16)
        return None
    
    def is_deregistration(self, assignment_type):
        """Check if the Server-Assignment-Type indicates deregistration."""
        deregistration_types = [
            SERVER_ASSIGNMENT_TIMEOUT_DEREGISTRATION,
            SERVER_ASSIGNMENT_USER_DEREGISTRATION,
            SERVER_ASSIGNMENT_DEREGISTRATION_STORE,
            SERVER_ASSIGNMENT_USER_DEREGISTRATION_STORE,
            SERVER_ASSIGNMENT_ADMINISTRATIVE_DEREGISTRATION,
            SERVER_ASSIGNMENT_AUTHENTICATION_FAILURE,
            SERVER_ASSIGNMENT_AUTHENTICATION_TIMEOUT,
            SERVER_ASSIGNMENT_DEREGISTRATION_TOO_MUCH_DATA
        ]
        return assignment_type in deregistration_types


# Factory function for integration with PyHSS
def create_swx_handler(diameter_instance):
    """
    Factory function to create SWx handler instance.
    
    Args:
        diameter_instance: Main PyHSS Diameter class instance
        
    Returns:
        DiameterSWx instance configured with the parent Diameter
    """
    return DiameterSWx(diameter_instance)
