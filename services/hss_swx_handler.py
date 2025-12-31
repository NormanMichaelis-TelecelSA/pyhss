"""
PyHSS SWx Service Handler
Handles SWx Diameter interface logic for non-3GPP access

This module provides the business logic for handling SWx messages:
- MAR: Authenticate subscriber for non-3GPP access
- SAR: Register AAA server, return subscriber profile
- RTR: Initiate de-registration
- PPR: Push profile updates

Author: PyHSS Community
License: AGPL-3.0
"""

import logging
import binascii
import time
import os
import sys

# Setup logging
logging.basicConfig(level=logging.DEBUG)
swx_handler_logger = logging.getLogger('SWxHandler')

# Import paths - adjust for PyHSS integration
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from lib.diameter_swx import (
        DiameterSWx, SWX_APPLICATION_ID, 
        DIAMETER_SUCCESS, DIAMETER_ERROR_USER_UNKNOWN,
        DIAMETER_ERROR_ROAMING_NOT_ALLOWED, DIAMETER_ERROR_USER_NO_APN_SUBSCRIPTION,
        DIAMETER_ERROR_AUTH_SCHEME_NOT_SUPPORTED,
        SERVER_ASSIGNMENT_REGISTRATION, SERVER_ASSIGNMENT_RE_REGISTRATION,
        SERVER_ASSIGNMENT_UNREGISTERED_USER, SERVER_ASSIGNMENT_AAA_USER_DATA_REQUEST,
        SERVER_ASSIGNMENT_TIMEOUT_DEREGISTRATION, SERVER_ASSIGNMENT_USER_DEREGISTRATION,
        REASON_PERMANENT_TERMINATION
    )
    from lib.models_swx import (
        get_swx_registration, create_or_update_swx_registration, deregister_swx,
        get_non_3gpp_subscription, get_swx_apn_configurations,
        create_default_non_3gpp_subscription
    )
except ImportError:
    # Fallback for development
    from diameter_swx import (
        DiameterSWx, SWX_APPLICATION_ID,
        DIAMETER_SUCCESS, DIAMETER_ERROR_USER_UNKNOWN,
        DIAMETER_ERROR_ROAMING_NOT_ALLOWED, DIAMETER_ERROR_USER_NO_APN_SUBSCRIPTION,
        DIAMETER_ERROR_AUTH_SCHEME_NOT_SUPPORTED,
        SERVER_ASSIGNMENT_REGISTRATION, SERVER_ASSIGNMENT_RE_REGISTRATION,
        SERVER_ASSIGNMENT_UNREGISTERED_USER, SERVER_ASSIGNMENT_AAA_USER_DATA_REQUEST,
        SERVER_ASSIGNMENT_TIMEOUT_DEREGISTRATION, SERVER_ASSIGNMENT_USER_DEREGISTRATION,
        REASON_PERMANENT_TERMINATION
    )
    from models_swx import (
        get_swx_registration, create_or_update_swx_registration, deregister_swx,
        get_non_3gpp_subscription, get_swx_apn_configurations,
        create_default_non_3gpp_subscription
    )


class SWxHandler:
    """
    SWx interface handler for PyHSS.
    
    This class processes SWx Diameter messages and implements the HSS-side
    logic for non-3GPP access authentication and authorization.
    """
    
    def __init__(self, diameter_instance, database_instance, yaml_config, redis_store=None):
        """
        Initialize SWx handler.
        
        Args:
            diameter_instance: Main PyHSS Diameter class instance
            database_instance: PyHSS database module instance
            yaml_config: PyHSS configuration dictionary
            redis_store: Redis connection for stats/caching (optional)
        """
        self.diameter = diameter_instance
        self.database = database_instance
        self.yaml_config = yaml_config
        self.redis_store = redis_store
        
        # Initialize SWx Diameter handler
        self.swx = DiameterSWx(diameter_instance)
        
        # Get SWx-specific config
        self.swx_config = yaml_config.get('swx', {})
        self.enabled = self.swx_config.get('enabled', False)
        self.default_apn = self.swx_config.get('default_apn', 'ims')
        self.auth_scheme = self.swx_config.get('auth_scheme', 'EAP-AKA')
        self.num_auth_vectors = self.swx_config.get('num_auth_vectors', 1)
        self.auto_create_subscription = self.swx_config.get('auto_create_non3gpp_subscription', True)
        
        swx_handler_logger.info(f"SWx Handler initialized, enabled={self.enabled}")
    
    def increment_stat(self, stat_name):
        """Increment Redis stat counter if available."""
        if self.redis_store:
            try:
                self.redis_store.incr(stat_name)
            except Exception as e:
                swx_handler_logger.debug(f"Failed to increment stat {stat_name}: {e}")
    
    # =========================================================================
    # MAR Handler - Multimedia-Auth-Request
    # =========================================================================
    
    def handle_mar(self, packet_vars, avps):
        """
        Handle Multimedia-Auth-Request from 3GPP AAA server.
        
        This generates EAP-AKA authentication vectors for the subscriber.
        
        Args:
            packet_vars: Decoded packet variables
            avps: List of decoded AVPs
            
        Returns:
            Diameter answer packet (hex string)
        """
        self.increment_stat('swx_mar_request_count')
        swx_handler_logger.info("Processing SWx MAR")
        
        try:
            # Extract IMSI from User-Name AVP
            user_name_avp = self.swx.get_avp_data(avps, 1)
            if not user_name_avp:
                swx_handler_logger.error("MAR missing User-Name AVP")
                self.increment_stat('swx_mar_error_count')
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            imsi = self.swx.extract_imsi_from_username(user_name_avp[0])
            if not imsi:
                swx_handler_logger.error("Could not extract IMSI from User-Name")
                self.increment_stat('swx_mar_error_count')
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            swx_handler_logger.info(f"MAR for IMSI: {imsi}")
            
            # Look up subscriber in database
            subscriber = self.database.GetObj(self.database.AUC, imsi, 'imsi')
            if not subscriber:
                swx_handler_logger.warning(f"Subscriber not found: {imsi}")
                self.increment_stat('swx_mar_user_unknown_count')
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            swx_handler_logger.debug(f"Found subscriber: {subscriber}")
            
            # Check if subscriber has non-3GPP access rights
            non_3gpp_sub = self._get_or_create_non3gpp_subscription(subscriber['subscriber_id'])
            if not non_3gpp_sub:
                swx_handler_logger.warning(f"Non-3GPP access not authorized for {imsi}")
                self.increment_stat('swx_mar_roaming_not_allowed_count')
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_ROAMING_NOT_ALLOWED
                )[0]
            
            # Check if non-3GPP IP access is allowed
            if non_3gpp_sub.get('non_3gpp_ip_access', 0) == 1:  # BARRED
                swx_handler_logger.warning(f"Non-3GPP IP access barred for {imsi}")
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_ROAMING_NOT_ALLOWED
                )[0]
            
            # Get number of vectors requested (default 1)
            num_vectors = non_3gpp_sub.get('num_auth_vectors', self.num_auth_vectors)
            sip_num_auth_items = self.swx.get_avp_data(avps, 607)  # SIP-Number-Auth-Items
            if sip_num_auth_items:
                try:
                    requested_vectors = int(sip_num_auth_items[0], 16)
                    num_vectors = min(requested_vectors, 5)  # Cap at 5 vectors
                except:
                    pass
            
            # Generate authentication vectors using AuC
            auth_vectors = self._generate_auth_vectors(subscriber, num_vectors)
            if not auth_vectors:
                swx_handler_logger.error(f"Failed to generate auth vectors for {imsi}")
                self.increment_stat('swx_mar_error_count')
                return self.swx.Answer_16777265_303_Error(
                    packet_vars, avps, DIAMETER_ERROR_AUTH_SCHEME_NOT_SUPPORTED
                )[0]
            
            # Build subscriber data for response
            subscriber_data = {
                'auth_scheme': non_3gpp_sub.get('auth_scheme', self.auth_scheme)
            }
            
            # Generate successful MAA
            response, result_code = self.swx.Answer_16777265_303(
                packet_vars, avps, subscriber_data, auth_vectors
            )
            
            self.increment_stat('swx_mar_success_count')
            swx_handler_logger.info(f"MAA success for {imsi} with {len(auth_vectors)} vector(s)")
            
            return response
            
        except Exception as e:
            swx_handler_logger.error(f"MAR processing error: {e}", exc_info=True)
            self.increment_stat('swx_mar_error_count')
            return self.swx.Answer_16777265_303_Error(
                packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
            )[0]
    
    def _generate_auth_vectors(self, subscriber, num_vectors=1):
        """
        Generate EAP-AKA authentication vectors for subscriber.
        
        Uses the existing PyHSS AuC to generate MILENAGE vectors,
        then formats them for SWx SIP-Auth-Data-Item.
        
        Args:
            subscriber: Subscriber AuC record
            num_vectors: Number of vectors to generate
            
        Returns:
            List of auth vector dicts with rand, autn, xres, ck, ik
        """
        vectors = []
        
        try:
            # Import PyHSS crypto utilities
            # These should be available from the diameter module
            from lib.CryptoTool import Milenage
        except ImportError:
            try:
                from CryptoTool import Milenage
            except ImportError:
                swx_handler_logger.error("Could not import Milenage crypto")
                return None
        
        # Get subscriber credentials
        ki = subscriber.get('ki')
        opc = subscriber.get('opc')
        amf = subscriber.get('amf', '8000')
        sqn = subscriber.get('sqn', 0)
        
        if not ki or not opc:
            swx_handler_logger.error("Missing Ki or OPc for subscriber")
            return None
        
        # Ensure proper format
        if isinstance(ki, str):
            ki = bytes.fromhex(ki)
        if isinstance(opc, str):
            opc = bytes.fromhex(opc)
        if isinstance(amf, str):
            amf = bytes.fromhex(amf)
        
        for i in range(num_vectors):
            try:
                # Generate RAND
                import secrets
                rand = secrets.token_bytes(16)
                
                # Increment SQN
                current_sqn = sqn + i
                sqn_bytes = current_sqn.to_bytes(6, byteorder='big')
                
                # Initialize Milenage
                milenage = Milenage(opc, ki)
                
                # Generate XRES, CK, IK, AUTN
                xres, ck, ik, autn = milenage.generate_vector(rand, sqn_bytes, amf)
                
                vector = {
                    'rand': rand.hex(),
                    'autn': autn.hex(),
                    'xres': xres.hex(),
                    'ck': ck.hex(),
                    'ik': ik.hex()
                }
                
                vectors.append(vector)
                swx_handler_logger.debug(f"Generated vector {i+1}: RAND={rand.hex()[:16]}...")
                
            except Exception as e:
                swx_handler_logger.error(f"Vector generation error: {e}")
                # Try alternate method using PyHSS diameter.generate_avp
                vector = self._generate_vector_pyhss(subscriber)
                if vector:
                    vectors.append(vector)
        
        # Update SQN in database
        if vectors:
            try:
                new_sqn = sqn + num_vectors
                self.database.UpdateObj(
                    self.database.AUC,
                    {'sqn': new_sqn},
                    subscriber['auc_id']
                )
            except Exception as e:
                swx_handler_logger.warning(f"Failed to update SQN: {e}")
        
        return vectors if vectors else None
    
    def _generate_vector_pyhss(self, subscriber):
        """
        Generate auth vector using PyHSS diameter module method.
        
        This is a fallback that uses the existing PyHSS vector generation.
        """
        try:
            # Use diameter module's existing vector generation
            # This replicates what S6a authentication does
            vector = self.diameter.generate_auth_vector(
                subscriber['ki'],
                subscriber['opc'],
                subscriber.get('amf', '8000'),
                subscriber.get('sqn', 0)
            )
            return vector
        except Exception as e:
            swx_handler_logger.error(f"PyHSS vector generation failed: {e}")
            return None
    
    # =========================================================================
    # SAR Handler - Server-Assignment-Request
    # =========================================================================
    
    def handle_sar(self, packet_vars, avps):
        """
        Handle Server-Assignment-Request from 3GPP AAA server.
        
        This registers the AAA server for the subscriber and returns
        the subscriber's non-3GPP profile.
        
        Args:
            packet_vars: Decoded packet variables
            avps: List of decoded AVPs
            
        Returns:
            Diameter answer packet (hex string)
        """
        self.increment_stat('swx_sar_request_count')
        swx_handler_logger.info("Processing SWx SAR")
        
        try:
            # Extract IMSI
            user_name_avp = self.swx.get_avp_data(avps, 1)
            if not user_name_avp:
                swx_handler_logger.error("SAR missing User-Name AVP")
                self.increment_stat('swx_sar_error_count')
                return self.swx.Answer_16777265_301_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            imsi = self.swx.extract_imsi_from_username(user_name_avp[0])
            if not imsi:
                swx_handler_logger.error("Could not extract IMSI from User-Name")
                self.increment_stat('swx_sar_error_count')
                return self.swx.Answer_16777265_301_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            swx_handler_logger.info(f"SAR for IMSI: {imsi}")
            
            # Get Server-Assignment-Type
            assignment_type = self.swx.get_server_assignment_type(avps)
            swx_handler_logger.info(f"Server-Assignment-Type: {assignment_type}")
            
            # Look up subscriber
            subscriber = self.database.GetObj(self.database.SUBSCRIBER, imsi, 'imsi')
            if not subscriber:
                swx_handler_logger.warning(f"Subscriber not found: {imsi}")
                self.increment_stat('swx_sar_user_unknown_count')
                return self.swx.Answer_16777265_301_Error(
                    packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
                )[0]
            
            # Handle deregistration types
            if self.swx.is_deregistration(assignment_type):
                return self._handle_sar_deregistration(packet_vars, avps, imsi, subscriber, assignment_type)
            
            # Handle registration types
            return self._handle_sar_registration(packet_vars, avps, imsi, subscriber, assignment_type)
            
        except Exception as e:
            swx_handler_logger.error(f"SAR processing error: {e}", exc_info=True)
            self.increment_stat('swx_sar_error_count')
            return self.swx.Answer_16777265_301_Error(
                packet_vars, avps, DIAMETER_ERROR_USER_UNKNOWN
            )[0]
    
    def _handle_sar_registration(self, packet_vars, avps, imsi, subscriber, assignment_type):
        """Handle SAR for registration types."""
        swx_handler_logger.info(f"SAR registration for {imsi}")
        
        # Get AAA server info from Origin-Host/Realm
        origin_host_avp = self.swx.get_avp_data(avps, 264)
        origin_realm_avp = self.swx.get_avp_data(avps, 296)
        
        aaa_server = binascii.unhexlify(origin_host_avp[0]).decode('utf-8') if origin_host_avp else 'unknown'
        aaa_realm = binascii.unhexlify(origin_realm_avp[0]).decode('utf-8') if origin_realm_avp else 'unknown'
        
        # Get session ID
        session_id_avp = self.swx.get_avp_data(avps, 263)
        session_id = binascii.unhexlify(session_id_avp[0]).decode('utf-8') if session_id_avp else None
        
        # Determine access type from AVPs
        access_type = 'UNTRUSTED_WLAN'  # Default for ePDG
        
        # Store/update registration
        try:
            # Using direct database operations for now
            # In production, this would use proper session management
            from sqlalchemy.orm import Session
            from sqlalchemy import create_engine
            
            # Get database session from PyHSS database module
            with self.database.get_session() as db_session:
                create_or_update_swx_registration(
                    db_session,
                    imsi=imsi,
                    subscriber_id=subscriber['subscriber_id'],
                    aaa_server_name=aaa_server,
                    aaa_realm=aaa_realm,
                    access_type=access_type,
                    session_id=session_id
                )
        except Exception as e:
            swx_handler_logger.warning(f"Could not store SWx registration: {e}")
            # Continue anyway - registration storage is non-critical
        
        # Get non-3GPP subscription data
        non_3gpp_sub = self._get_or_create_non3gpp_subscription(subscriber['subscriber_id'])
        if not non_3gpp_sub:
            swx_handler_logger.warning(f"No non-3GPP subscription for {imsi}")
            return self.swx.Answer_16777265_301_Error(
                packet_vars, avps, DIAMETER_ERROR_USER_NO_APN_SUBSCRIPTION
            )[0]
        
        # Build subscriber data for response
        subscriber_data = {
            'non_3gpp_ip_access': non_3gpp_sub.get('non_3gpp_ip_access', 0),
            'non_3gpp_ip_access_apn': non_3gpp_sub.get('non_3gpp_ip_access_apn', 0),
            'an_trusted': non_3gpp_sub.get('an_trusted', 1),
            'max_ul': non_3gpp_sub.get('max_requested_bandwidth_ul', 100000000),
            'max_dl': non_3gpp_sub.get('max_requested_bandwidth_dl', 100000000)
        }
        
        # Get APN configurations
        apn_configs = self._get_apn_configurations(subscriber['subscriber_id'], non_3gpp_sub)
        
        # Generate successful SAA
        response, result_code = self.swx.Answer_16777265_301(
            packet_vars, avps, subscriber_data, apn_configs
        )
        
        self.increment_stat('swx_sar_success_count')
        swx_handler_logger.info(f"SAA success for {imsi}, registered to {aaa_server}")
        
        return response
    
    def _handle_sar_deregistration(self, packet_vars, avps, imsi, subscriber, assignment_type):
        """Handle SAR for deregistration types."""
        swx_handler_logger.info(f"SAR deregistration for {imsi}, type={assignment_type}")
        
        # Remove registration from database
        try:
            with self.database.get_session() as db_session:
                deregister_swx(db_session, imsi, reason_code=assignment_type)
        except Exception as e:
            swx_handler_logger.warning(f"Could not remove SWx registration: {e}")
        
        # Return success - minimal SAA for deregistration
        subscriber_data = {'non_3gpp_ip_access': 0, 'an_trusted': 1}
        
        response, result_code = self.swx.Answer_16777265_301(
            packet_vars, avps, subscriber_data, []
        )
        
        self.increment_stat('swx_sar_deregistration_count')
        swx_handler_logger.info(f"SAA deregistration success for {imsi}")
        
        return response
    
    def _get_or_create_non3gpp_subscription(self, subscriber_id):
        """Get or create non-3GPP subscription for subscriber."""
        try:
            with self.database.get_session() as db_session:
                subscription = get_non_3gpp_subscription(db_session, subscriber_id)
                
                if subscription:
                    return subscription.to_dict()
                
                # Auto-create if enabled
                if self.auto_create_subscription:
                    swx_handler_logger.info(f"Auto-creating non-3GPP subscription for {subscriber_id}")
                    subscription = create_default_non_3gpp_subscription(
                        db_session, subscriber_id, self.default_apn
                    )
                    return subscription.to_dict()
                
                return None
                
        except Exception as e:
            swx_handler_logger.warning(f"Error getting non-3GPP subscription: {e}")
            # Return default subscription data
            if self.auto_create_subscription:
                return {
                    'non_3gpp_ip_access': 0,
                    'non_3gpp_ip_access_apn': 0,
                    'an_trusted': 1,
                    'max_requested_bandwidth_ul': 100000000,
                    'max_requested_bandwidth_dl': 100000000,
                    'auth_scheme': self.auth_scheme,
                    'num_auth_vectors': self.num_auth_vectors,
                    'default_apn': self.default_apn
                }
            return None
    
    def _get_apn_configurations(self, subscriber_id, non_3gpp_sub):
        """Get APN configurations for subscriber."""
        apn_configs = []
        
        try:
            # Try to get from SWx-specific APN table
            with self.database.get_session() as db_session:
                non_3gpp_subscription = get_non_3gpp_subscription(db_session, subscriber_id)
                if non_3gpp_subscription:
                    configs = get_swx_apn_configurations(db_session, non_3gpp_subscription.id)
                    apn_configs = [c.to_apn_config_dict() for c in configs]
        except Exception as e:
            swx_handler_logger.debug(f"Could not get SWx APN configs: {e}")
        
        # Fall back to subscriber's regular APNs
        if not apn_configs:
            try:
                # Get subscriber's APN list from standard tables
                apns = self.database.Get_APN_list(subscriber_id)
                for apn in apns:
                    apn_config = {
                        'context_identifier': apn.get('apn_id', 1),
                        'apn': apn.get('apn', self.default_apn),
                        'pdn_type': 0,  # IPv4
                        'vplmn_dynamic_address_allowed': 1,
                        'max_ul': apn.get('apn_ambr_ul', 50000000),
                        'max_dl': apn.get('apn_ambr_dl', 100000000),
                        'qos_profile': {
                            'qci': apn.get('qci', 9),
                            'priority_level': apn.get('arp_priority', 8),
                            'preemption_capability': apn.get('arp_preemption_capability', 1),
                            'preemption_vulnerability': apn.get('arp_preemption_vulnerability', 0)
                        }
                    }
                    apn_configs.append(apn_config)
            except Exception as e:
                swx_handler_logger.debug(f"Could not get standard APNs: {e}")
        
        # Default IMS APN if nothing found
        if not apn_configs:
            apn_configs.append({
                'context_identifier': 1,
                'apn': self.default_apn,
                'pdn_type': 0,
                'vplmn_dynamic_address_allowed': 1,
                'max_ul': 50000000,
                'max_dl': 100000000,
                'qos_profile': {
                    'qci': 5,  # IMS signaling
                    'priority_level': 1,
                    'preemption_capability': 0,
                    'preemption_vulnerability': 0
                }
            })
        
        return apn_configs
    
    # =========================================================================
    # RTR Handler - Registration-Termination-Request (HSS-initiated)
    # =========================================================================
    
    def send_rtr(self, imsi, reason_code=REASON_PERMANENT_TERMINATION, reason_info=None):
        """
        Send Registration-Termination-Request to deregister subscriber.
        
        This is called by the HSS to deregister a subscriber from non-3GPP access.
        
        Args:
            imsi: Subscriber IMSI
            reason_code: Deregistration reason
            reason_info: Optional reason text
            
        Returns:
            Tuple of (success, message)
        """
        swx_handler_logger.info(f"Initiating RTR for {imsi}")
        self.increment_stat('swx_rtr_sent_count')
        
        try:
            # Get current registration to find AAA server
            with self.database.get_session() as db_session:
                registration = get_swx_registration(db_session, imsi=imsi, active_only=True)
                
                if not registration:
                    swx_handler_logger.warning(f"No active SWx registration for {imsi}")
                    return False, "No active registration found"
                
                destination_host = registration.aaa_server_name
                destination_realm = registration.aaa_realm
                
                # Generate RTR
                rtr_packet = self.swx.Request_16777265_304(
                    imsi=imsi,
                    destination_host=destination_host,
                    destination_realm=destination_realm,
                    reason_code=reason_code,
                    reason_info=reason_info
                )
                
                # Queue for sending via diameter service
                # This uses Redis to communicate with diameterService
                if self.redis_store:
                    message = {
                        'type': 'diameter_request',
                        'destination_host': destination_host,
                        'destination_realm': destination_realm,
                        'application_id': SWX_APPLICATION_ID,
                        'command_code': 304,
                        'packet': rtr_packet
                    }
                    self.redis_store.publish('diameter_outbound', str(message))
                
                swx_handler_logger.info(f"RTR queued for {imsi} to {destination_host}")
                return True, f"RTR sent to {destination_host}"
                
        except Exception as e:
            swx_handler_logger.error(f"RTR send error: {e}")
            self.increment_stat('swx_rtr_error_count')
            return False, str(e)
    
    def handle_rta(self, packet_vars, avps):
        """
        Handle Registration-Termination-Answer from AAA server.
        
        Args:
            packet_vars: Decoded packet variables
            avps: List of decoded AVPs
        """
        swx_handler_logger.info("Processing SWx RTA")
        self.increment_stat('swx_rta_received_count')
        
        # Extract result code
        result_code_avp = self.swx.get_avp_data(avps, 268)
        if result_code_avp:
            result_code = int(result_code_avp[0], 16)
            if result_code == DIAMETER_SUCCESS:
                swx_handler_logger.info("RTA success")
            else:
                swx_handler_logger.warning(f"RTA result code: {result_code}")
    
    # =========================================================================
    # PPR Handler - Push-Profile-Request (HSS-initiated)
    # =========================================================================
    
    def send_ppr(self, imsi):
        """
        Send Push-Profile-Request to update subscriber profile at AAA.
        
        Args:
            imsi: Subscriber IMSI
            
        Returns:
            Tuple of (success, message)
        """
        swx_handler_logger.info(f"Initiating PPR for {imsi}")
        self.increment_stat('swx_ppr_sent_count')
        
        try:
            # Get subscriber and registration
            subscriber = self.database.GetObj(self.database.SUBSCRIBER, imsi, 'imsi')
            if not subscriber:
                return False, "Subscriber not found"
            
            with self.database.get_session() as db_session:
                registration = get_swx_registration(db_session, imsi=imsi, active_only=True)
                
                if not registration:
                    swx_handler_logger.warning(f"No active SWx registration for {imsi}")
                    return False, "No active registration found"
                
                destination_host = registration.aaa_server_name
                destination_realm = registration.aaa_realm
                
                # Get updated subscription data
                non_3gpp_sub = self._get_or_create_non3gpp_subscription(subscriber['subscriber_id'])
                apn_configs = self._get_apn_configurations(subscriber['subscriber_id'], non_3gpp_sub)
                
                subscriber_data = {
                    'non_3gpp_ip_access': non_3gpp_sub.get('non_3gpp_ip_access', 0),
                    'non_3gpp_ip_access_apn': non_3gpp_sub.get('non_3gpp_ip_access_apn', 0),
                    'an_trusted': non_3gpp_sub.get('an_trusted', 1),
                    'max_ul': non_3gpp_sub.get('max_requested_bandwidth_ul', 100000000),
                    'max_dl': non_3gpp_sub.get('max_requested_bandwidth_dl', 100000000)
                }
                
                # Generate PPR
                ppr_packet = self.swx.Request_16777265_305(
                    imsi=imsi,
                    destination_host=destination_host,
                    destination_realm=destination_realm,
                    subscriber_data=subscriber_data,
                    apn_configs=apn_configs
                )
                
                # Queue for sending
                if self.redis_store:
                    message = {
                        'type': 'diameter_request',
                        'destination_host': destination_host,
                        'destination_realm': destination_realm,
                        'application_id': SWX_APPLICATION_ID,
                        'command_code': 305,
                        'packet': ppr_packet
                    }
                    self.redis_store.publish('diameter_outbound', str(message))
                
                swx_handler_logger.info(f"PPR queued for {imsi} to {destination_host}")
                return True, f"PPR sent to {destination_host}"
                
        except Exception as e:
            swx_handler_logger.error(f"PPR send error: {e}")
            self.increment_stat('swx_ppr_error_count')
            return False, str(e)
    
    def handle_ppa(self, packet_vars, avps):
        """
        Handle Push-Profile-Answer from AAA server.
        
        Args:
            packet_vars: Decoded packet variables
            avps: List of decoded AVPs
        """
        swx_handler_logger.info("Processing SWx PPA")
        self.increment_stat('swx_ppa_received_count')
        
        result_code_avp = self.swx.get_avp_data(avps, 268)
        if result_code_avp:
            result_code = int(result_code_avp[0], 16)
            if result_code == DIAMETER_SUCCESS:
                swx_handler_logger.info("PPA success")
            else:
                swx_handler_logger.warning(f"PPA result code: {result_code}")


# ============================================================================
# Integration functions for PyHSS hssService.py
# ============================================================================

def process_swx_request(handler, packet_vars, avps):
    """
    Main entry point for processing SWx requests.
    
    This function routes SWx requests to the appropriate handler.
    
    Args:
        handler: SWxHandler instance
        packet_vars: Decoded packet variables (includes command_code)
        avps: List of decoded AVPs
        
    Returns:
        Diameter answer packet (hex string)
    """
    command_code = packet_vars.get('command_code')
    
    if command_code == 303:  # MAR
        return handler.handle_mar(packet_vars, avps)
    elif command_code == 301:  # SAR
        return handler.handle_sar(packet_vars, avps)
    elif command_code == 304:  # RTA (answer to our RTR)
        handler.handle_rta(packet_vars, avps)
        return None  # No response needed
    elif command_code == 305:  # PPA (answer to our PPR)
        handler.handle_ppa(packet_vars, avps)
        return None  # No response needed
    else:
        swx_handler_logger.error(f"Unknown SWx command code: {command_code}")
        return None


def create_swx_handler(diameter_instance, database_instance, yaml_config, redis_store=None):
    """
    Factory function to create SWxHandler instance.
    
    Args:
        diameter_instance: Main PyHSS Diameter class instance
        database_instance: PyHSS database module instance
        yaml_config: PyHSS configuration dictionary
        redis_store: Redis connection (optional)
        
    Returns:
        SWxHandler instance
    """
    return SWxHandler(diameter_instance, database_instance, yaml_config, redis_store)
