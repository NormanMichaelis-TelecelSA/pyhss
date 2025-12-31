"""
PyHSS SWx Addon Tests
Unit tests for SWx Diameter interface implementation

Run with: python -m pytest tests/test_swx.py -v
"""

import pytest
import binascii
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockDiameter:
    """Mock Diameter class for testing."""
    
    def __init__(self):
        self.OriginHost = binascii.hexlify(b"hss.example.com").decode('ascii')
        self.OriginRealm = binascii.hexlify(b"example.com").decode('ascii')
        self.ProductName = "PyHSS-Test"
        self.MCC = "001"
        self.MNC = "01"
    
    def generate_avp(self, avp_code, avp_flags, avp_content):
        """Simple AVP generator for testing."""
        avp_code_hex = format(avp_code, 'x').zfill(8)
        avp_content_len = len(avp_content) // 2 + 8
        avp_length_hex = format(avp_content_len, 'x').zfill(6)
        return f"{avp_code_hex}{avp_flags}{avp_length_hex}{avp_content}"
    
    def generate_vendor_avp(self, avp_code, avp_flags, vendor_id, avp_content):
        """Simple vendor AVP generator for testing."""
        avp_code_hex = format(avp_code, 'x').zfill(8)
        vendor_id_hex = format(vendor_id, 'x').zfill(8)
        avp_content_len = len(avp_content) // 2 + 12
        avp_length_hex = format(avp_content_len, 'x').zfill(6)
        return f"{avp_code_hex}{avp_flags}{avp_length_hex}{vendor_id_hex}{avp_content}"
    
    def generate_diameter_packet(self, version, flags, cmd_code, app_id, hbh, ete, avp):
        """Simple packet generator for testing."""
        return f"01{flags}{format(cmd_code, 'x').zfill(6)}{app_id}{hbh}{ete}{avp}"
    
    def get_avp_data(self, avps, avp_code):
        """Mock AVP data getter."""
        for avp in avps:
            if avp.get('avp_code') == avp_code:
                return [avp.get('misc_data', '')]
        return []


class TestDiameterSWx:
    """Tests for DiameterSWx class."""
    
    @pytest.fixture
    def swx(self):
        """Create SWx instance for testing."""
        from lib.diameter_swx import DiameterSWx
        mock_diameter = MockDiameter()
        return DiameterSWx(mock_diameter)
    
    def test_init(self, swx):
        """Test SWx initialization."""
        assert swx.OriginHost is not None
        assert swx.OriginRealm is not None
    
    def test_int_to_hex(self, swx):
        """Test int to hex conversion."""
        assert swx.int_to_hex(256, 2) == "0100"
        assert swx.int_to_hex(1, 4) == "00000001"
        assert swx.int_to_hex(0, 1) == "00"
    
    def test_extract_imsi_from_username_bare(self, swx):
        """Test IMSI extraction from bare IMSI."""
        username_hex = binascii.hexlify(b"001010000000001").decode('ascii')
        imsi = swx.extract_imsi_from_username(username_hex)
        assert imsi == "001010000000001"
    
    def test_extract_imsi_from_username_nai(self, swx):
        """Test IMSI extraction from NAI format."""
        username = "0001010000000001@nai.epc.mnc001.mcc001.3gppnetwork.org"
        username_hex = binascii.hexlify(username.encode('utf-8')).decode('ascii')
        imsi = swx.extract_imsi_from_username(username_hex)
        assert imsi == "001010000000001"
    
    def test_extract_imsi_from_username_decorated_nai(self, swx):
        """Test IMSI extraction from decorated NAI format."""
        username = "wlan!0001010000000001@nai.epc.mnc001.mcc001.3gppnetwork.org"
        username_hex = binascii.hexlify(username.encode('utf-8')).decode('ascii')
        imsi = swx.extract_imsi_from_username(username_hex)
        assert imsi == "001010000000001"
    
    def test_generate_sip_auth_data_item(self, swx):
        """Test SIP-Auth-Data-Item AVP generation."""
        rand = "00" * 16  # 16 bytes of zeros
        autn = "11" * 16
        xres = "22" * 8
        ck = "33" * 16
        ik = "44" * 16
        
        result = swx.generate_sip_auth_data_item(rand, autn, xres, ck, ik, "EAP-AKA")
        
        assert result is not None
        assert len(result) > 0
        # Should contain AVP code 612 (SIP-Auth-Data-Item)
        assert "00000264" in result  # 612 in hex = 264
    
    def test_generate_apn_configuration(self, swx):
        """Test APN-Configuration AVP generation."""
        apn_config = {
            'context_identifier': 1,
            'apn': 'ims',
            'pdn_type': 0,
            'vplmn_dynamic_address_allowed': 1,
            'max_ul': 50000000,
            'max_dl': 100000000,
            'qos_profile': {
                'qci': 5,
                'priority_level': 1,
                'preemption_capability': 0,
                'preemption_vulnerability': 0
            }
        }
        
        result = swx.generate_apn_configuration(apn_config)
        
        assert result is not None
        assert len(result) > 0
        # Should contain AVP code 1430 (APN-Configuration)
        assert "00000596" in result  # 1430 in hex = 596
    
    def test_generate_non_3gpp_user_data(self, swx):
        """Test Non-3GPP-User-Data AVP generation."""
        subscriber_data = {
            'non_3gpp_ip_access': 0,
            'non_3gpp_ip_access_apn': 0,
            'an_trusted': 1,
            'max_ul': 100000000,
            'max_dl': 100000000
        }
        
        apn_configs = [{
            'context_identifier': 1,
            'apn': 'ims',
            'pdn_type': 0,
            'vplmn_dynamic_address_allowed': 1
        }]
        
        result = swx.generate_non_3gpp_user_data(subscriber_data, apn_configs)
        
        assert result is not None
        assert len(result) > 0
        # Should contain AVP code 1500 (Non-3GPP-User-Data)
        assert "000005dc" in result  # 1500 in hex = 5dc
    
    def test_is_deregistration(self, swx):
        """Test deregistration type detection."""
        from lib.diameter_swx import (
            SERVER_ASSIGNMENT_REGISTRATION,
            SERVER_ASSIGNMENT_USER_DEREGISTRATION
        )
        
        assert swx.is_deregistration(SERVER_ASSIGNMENT_USER_DEREGISTRATION) is True
        assert swx.is_deregistration(SERVER_ASSIGNMENT_REGISTRATION) is False


class TestSWxConstants:
    """Tests for SWx constants and values."""
    
    def test_application_id(self):
        """Test SWx Application ID."""
        from lib.diameter_swx import SWX_APPLICATION_ID
        assert SWX_APPLICATION_ID == 16777265
    
    def test_command_codes(self):
        """Test SWx command codes."""
        from lib.diameter_swx import SWX_CMD_MAR, SWX_CMD_SAR, SWX_CMD_RTR, SWX_CMD_PPR
        assert SWX_CMD_MAR == 303
        assert SWX_CMD_SAR == 301
        assert SWX_CMD_RTR == 304
        assert SWX_CMD_PPR == 305
    
    def test_result_codes(self):
        """Test Diameter result codes."""
        from lib.diameter_swx import (
            DIAMETER_SUCCESS,
            DIAMETER_ERROR_USER_UNKNOWN,
            DIAMETER_ERROR_ROAMING_NOT_ALLOWED
        )
        assert DIAMETER_SUCCESS == 2001
        assert DIAMETER_ERROR_USER_UNKNOWN == 5001
        assert DIAMETER_ERROR_ROAMING_NOT_ALLOWED == 5004


class TestSWxModels:
    """Tests for SWx database models."""
    
    def test_swx_registration_to_dict(self):
        """Test SWX_REGISTRATION.to_dict()."""
        from lib.models_swx import SWX_REGISTRATION
        from datetime import datetime
        
        reg = SWX_REGISTRATION(
            id=1,
            subscriber_id=100,
            imsi="001010000000001",
            aaa_server_name="aaa.example.com",
            aaa_realm="example.com",
            is_active=True
        )
        reg.registration_time = datetime.now()
        
        result = reg.to_dict()
        
        assert result['id'] == 1
        assert result['imsi'] == "001010000000001"
        assert result['aaa_server_name'] == "aaa.example.com"
        assert result['is_active'] is True
    
    def test_non_3gpp_subscription_to_dict(self):
        """Test NON_3GPP_SUBSCRIPTION.to_dict()."""
        from lib.models_swx import NON_3GPP_SUBSCRIPTION
        
        sub = NON_3GPP_SUBSCRIPTION(
            id=1,
            subscriber_id=100,
            non_3gpp_ip_access=0,
            an_trusted=1,
            default_apn="ims"
        )
        
        result = sub.to_dict()
        
        assert result['subscriber_id'] == 100
        assert result['non_3gpp_ip_access'] == 0
        assert result['an_trusted'] == 1
        assert result['default_apn'] == "ims"
    
    def test_swx_apn_configuration_to_apn_config_dict(self):
        """Test SWX_APN_CONFIGURATION.to_apn_config_dict()."""
        from lib.models_swx import SWX_APN_CONFIGURATION
        
        config = SWX_APN_CONFIGURATION(
            id=1,
            non_3gpp_subscription_id=1,
            context_identifier=1,
            apn="ims",
            pdn_type=0,
            qos_class_identifier=5,
            priority_level=1,
            max_requested_bandwidth_ul=50000000,
            max_requested_bandwidth_dl=100000000
        )
        
        result = config.to_apn_config_dict()
        
        assert result['apn'] == "ims"
        assert result['pdn_type'] == 0
        assert result['max_ul'] == 50000000
        assert result['qos_profile']['qci'] == 5


class TestSWxIntegration:
    """Integration tests for SWx addon."""
    
    def test_swx_init_disabled(self):
        """Test SWx initialization when disabled."""
        from swx_init import init_swx
        
        config = {'swx': {'enabled': False}}
        result = init_swx(MockDiameter(), None, config, None, None)
        
        assert result is None
    
    def test_get_swx_config_defaults(self):
        """Test SWx config with defaults."""
        from swx_init import get_swx_config
        
        config = {}
        result = get_swx_config(config)
        
        assert result['enabled'] is False
        assert result['application_id'] == 16777265
        assert result['default_apn'] == 'ims'
        assert result['auth_scheme'] == 'EAP-AKA'
    
    def test_validate_swx_config_valid(self):
        """Test valid SWx configuration."""
        from swx_init import validate_swx_config
        
        config = {
            'swx': {
                'enabled': True,
                'auth_scheme': 'EAP-AKA',
                'num_auth_vectors': 1
            }
        }
        
        is_valid, message = validate_swx_config(config)
        assert is_valid is True
    
    def test_validate_swx_config_invalid_scheme(self):
        """Test invalid auth scheme."""
        from swx_init import validate_swx_config
        
        config = {
            'swx': {
                'enabled': True,
                'auth_scheme': 'INVALID'
            }
        }
        
        is_valid, message = validate_swx_config(config)
        assert is_valid is False
        assert "auth_scheme" in message
    
    def test_is_swx_message(self):
        """Test SWx message detection."""
        from swx_init import is_swx_message, SWX_APPLICATION_ID
        
        swx_packet = {'ApplicationId': SWX_APPLICATION_ID}
        s6a_packet = {'ApplicationId': 16777251}
        
        assert is_swx_message(swx_packet) is True
        assert is_swx_message(s6a_packet) is False
    
    def test_get_swx_command_name(self):
        """Test command name lookup."""
        from swx_init import get_swx_command_name
        
        assert get_swx_command_name(303, True) == "MAR"
        assert get_swx_command_name(303, False) == "MAA"
        assert get_swx_command_name(301, True) == "SAR"
        assert get_swx_command_name(999, True) == "Unknown-999"


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
