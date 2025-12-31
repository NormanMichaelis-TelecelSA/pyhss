"""
PyHSS SWx API Endpoints
REST API for managing SWx interface and non-3GPP subscriptions

This module provides Flask/Quart API endpoints for:
- Viewing/managing SWx registrations
- Managing non-3GPP subscription data
- Initiating RTR/PPR operations

Author: PyHSS Community
License: AGPL-3.0
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import logging

# Setup logging
api_logger = logging.getLogger('SWxAPI')

# Create Blueprint for SWx API
swx_api = Blueprint('swx_api', __name__, url_prefix='/swx')


def get_swx_handler():
    """Get SWx handler from app context."""
    from flask import current_app
    return current_app.config.get('SWX_HANDLER')


def get_database():
    """Get database module from app context."""
    from flask import current_app
    return current_app.config.get('DATABASE')


def require_swx_enabled(f):
    """Decorator to check if SWx is enabled."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        handler = get_swx_handler()
        if not handler or not handler.enabled:
            return jsonify({'error': 'SWx interface is not enabled'}), 503
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# SWx Registration Endpoints
# ============================================================================

@swx_api.route('/registrations', methods=['GET'])
@require_swx_enabled
def get_all_registrations():
    """
    Get all SWx registrations.
    
    Query params:
        active_only: bool (default True) - Only return active registrations
        limit: int (default 100) - Maximum number of results
        offset: int (default 0) - Offset for pagination
    
    Returns:
        JSON list of registrations
    """
    try:
        database = get_database()
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        from lib.models_swx import SWX_REGISTRATION
        
        with database.get_session() as session:
            query = session.query(SWX_REGISTRATION)
            
            if active_only:
                query = query.filter(SWX_REGISTRATION.is_active == True)
            
            total = query.count()
            registrations = query.offset(offset).limit(limit).all()
            
            return jsonify({
                'total': total,
                'offset': offset,
                'limit': limit,
                'registrations': [r.to_dict() for r in registrations]
            })
            
    except Exception as e:
        api_logger.error(f"Error getting registrations: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/registration/<imsi>', methods=['GET'])
@require_swx_enabled  
def get_registration(imsi):
    """
    Get SWx registration for a specific IMSI.
    
    Args:
        imsi: Subscriber IMSI (path parameter)
        
    Returns:
        JSON registration object or 404
    """
    try:
        database = get_database()
        from lib.models_swx import get_swx_registration
        
        with database.get_session() as session:
            registration = get_swx_registration(session, imsi=imsi, active_only=False)
            
            if not registration:
                return jsonify({'error': 'Registration not found'}), 404
            
            return jsonify(registration.to_dict())
            
    except Exception as e:
        api_logger.error(f"Error getting registration: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/registration/<imsi>', methods=['DELETE'])
@require_swx_enabled
def delete_registration(imsi):
    """
    Delete (deregister) SWx registration for an IMSI.
    
    This will also send an RTR to the AAA server if active.
    
    Args:
        imsi: Subscriber IMSI (path parameter)
        
    Query params:
        send_rtr: bool (default True) - Send RTR to AAA
        reason: int (default 0) - Deregistration reason code
        
    Returns:
        JSON result
    """
    try:
        handler = get_swx_handler()
        database = get_database()
        
        send_rtr = request.args.get('send_rtr', 'true').lower() == 'true'
        reason_code = int(request.args.get('reason', 0))
        
        # Send RTR first if requested
        if send_rtr:
            success, message = handler.send_rtr(imsi, reason_code=reason_code)
            if not success:
                api_logger.warning(f"RTR failed for {imsi}: {message}")
        
        # Remove registration from database
        from lib.models_swx import deregister_swx
        
        with database.get_session() as session:
            result = deregister_swx(session, imsi, reason_code=reason_code)
            
            if result:
                return jsonify({
                    'success': True,
                    'message': f'Registration deactivated for {imsi}',
                    'rtr_sent': send_rtr
                })
            else:
                return jsonify({'error': 'No active registration found'}), 404
                
    except Exception as e:
        api_logger.error(f"Error deleting registration: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Non-3GPP Subscription Endpoints
# ============================================================================

@swx_api.route('/subscription/<int:subscriber_id>', methods=['GET'])
@require_swx_enabled
def get_non3gpp_subscription(subscriber_id):
    """
    Get non-3GPP subscription for a subscriber.
    
    Args:
        subscriber_id: Subscriber ID (path parameter)
        
    Returns:
        JSON subscription object or 404
    """
    try:
        database = get_database()
        from lib.models_swx import get_non_3gpp_subscription
        
        with database.get_session() as session:
            subscription = get_non_3gpp_subscription(session, subscriber_id)
            
            if not subscription:
                return jsonify({'error': 'Non-3GPP subscription not found'}), 404
            
            return jsonify(subscription.to_dict())
            
    except Exception as e:
        api_logger.error(f"Error getting subscription: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/subscription/<int:subscriber_id>', methods=['PUT'])
@require_swx_enabled
def create_or_update_subscription(subscriber_id):
    """
    Create or update non-3GPP subscription.
    
    Args:
        subscriber_id: Subscriber ID (path parameter)
        
    Body (JSON):
        non_3gpp_ip_access: int (0=allowed, 1=barred)
        non_3gpp_ip_access_apn: int (0=enabled, 1=disabled)
        an_trusted: int (0=trusted, 1=untrusted)
        max_requested_bandwidth_ul: int
        max_requested_bandwidth_dl: int
        auth_scheme: str (EAP-AKA, EAP-AKA')
        allowed_apns: str (comma-separated)
        default_apn: str
        
    Returns:
        JSON subscription object
    """
    try:
        database = get_database()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        from lib.models_swx import NON_3GPP_SUBSCRIPTION, get_non_3gpp_subscription
        
        with database.get_session() as session:
            subscription = get_non_3gpp_subscription(session, subscriber_id)
            
            if subscription:
                # Update existing
                for key, value in data.items():
                    if hasattr(subscription, key):
                        setattr(subscription, key, value)
                session.commit()
                return jsonify(subscription.to_dict())
            else:
                # Create new
                subscription = NON_3GPP_SUBSCRIPTION(
                    subscriber_id=subscriber_id,
                    **{k: v for k, v in data.items() if hasattr(NON_3GPP_SUBSCRIPTION, k)}
                )
                session.add(subscription)
                session.commit()
                return jsonify(subscription.to_dict()), 201
                
    except Exception as e:
        api_logger.error(f"Error updating subscription: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/subscription/<int:subscriber_id>', methods=['DELETE'])
@require_swx_enabled
def delete_subscription(subscriber_id):
    """
    Delete non-3GPP subscription.
    
    Args:
        subscriber_id: Subscriber ID (path parameter)
        
    Returns:
        JSON result
    """
    try:
        database = get_database()
        from lib.models_swx import get_non_3gpp_subscription
        
        with database.get_session() as session:
            subscription = get_non_3gpp_subscription(session, subscriber_id)
            
            if not subscription:
                return jsonify({'error': 'Subscription not found'}), 404
            
            subscription.is_active = False
            session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Non-3GPP subscription deactivated for subscriber {subscriber_id}'
            })
            
    except Exception as e:
        api_logger.error(f"Error deleting subscription: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# APN Configuration Endpoints
# ============================================================================

@swx_api.route('/subscription/<int:subscriber_id>/apns', methods=['GET'])
@require_swx_enabled
def get_subscription_apns(subscriber_id):
    """
    Get APN configurations for non-3GPP subscription.
    
    Args:
        subscriber_id: Subscriber ID (path parameter)
        
    Returns:
        JSON list of APN configurations
    """
    try:
        database = get_database()
        from lib.models_swx import get_non_3gpp_subscription, get_swx_apn_configurations
        
        with database.get_session() as session:
            subscription = get_non_3gpp_subscription(session, subscriber_id)
            
            if not subscription:
                return jsonify({'error': 'Non-3GPP subscription not found'}), 404
            
            apn_configs = get_swx_apn_configurations(session, subscription.id)
            
            return jsonify({
                'subscription_id': subscription.id,
                'apn_configurations': [c.to_dict() for c in apn_configs]
            })
            
    except Exception as e:
        api_logger.error(f"Error getting APN configs: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/subscription/<int:subscriber_id>/apn', methods=['POST'])
@require_swx_enabled
def add_subscription_apn(subscriber_id):
    """
    Add APN configuration to non-3GPP subscription.
    
    Args:
        subscriber_id: Subscriber ID (path parameter)
        
    Body (JSON):
        apn: str (required) - APN name
        context_identifier: int
        pdn_type: int (0=IPv4, 1=IPv6, 2=IPv4v6)
        qos_class_identifier: int
        max_requested_bandwidth_ul: int
        max_requested_bandwidth_dl: int
        
    Returns:
        JSON APN configuration object
    """
    try:
        database = get_database()
        data = request.get_json()
        
        if not data or 'apn' not in data:
            return jsonify({'error': 'APN name required'}), 400
        
        from lib.models_swx import (
            get_non_3gpp_subscription, 
            SWX_APN_CONFIGURATION
        )
        
        with database.get_session() as session:
            subscription = get_non_3gpp_subscription(session, subscriber_id)
            
            if not subscription:
                return jsonify({'error': 'Non-3GPP subscription not found'}), 404
            
            # Get next context ID
            existing_configs = session.query(SWX_APN_CONFIGURATION).filter(
                SWX_APN_CONFIGURATION.non_3gpp_subscription_id == subscription.id
            ).all()
            
            next_context = max([c.context_identifier for c in existing_configs], default=0) + 1
            
            apn_config = SWX_APN_CONFIGURATION(
                non_3gpp_subscription_id=subscription.id,
                context_identifier=data.get('context_identifier', next_context),
                apn=data['apn'],
                pdn_type=data.get('pdn_type', 0),
                qos_class_identifier=data.get('qos_class_identifier', 9),
                priority_level=data.get('priority_level', 8),
                max_requested_bandwidth_ul=data.get('max_requested_bandwidth_ul', 50000000),
                max_requested_bandwidth_dl=data.get('max_requested_bandwidth_dl', 100000000),
                is_active=True
            )
            
            session.add(apn_config)
            session.commit()
            
            return jsonify(apn_config.to_dict()), 201
            
    except Exception as e:
        api_logger.error(f"Error adding APN config: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/apn/<int:apn_config_id>', methods=['DELETE'])
@require_swx_enabled
def delete_apn_config(apn_config_id):
    """
    Delete APN configuration.
    
    Args:
        apn_config_id: APN configuration ID (path parameter)
        
    Returns:
        JSON result
    """
    try:
        database = get_database()
        from lib.models_swx import SWX_APN_CONFIGURATION
        
        with database.get_session() as session:
            config = session.query(SWX_APN_CONFIGURATION).filter(
                SWX_APN_CONFIGURATION.id == apn_config_id
            ).first()
            
            if not config:
                return jsonify({'error': 'APN configuration not found'}), 404
            
            config.is_active = False
            session.commit()
            
            return jsonify({
                'success': True,
                'message': f'APN configuration {apn_config_id} deactivated'
            })
            
    except Exception as e:
        api_logger.error(f"Error deleting APN config: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Operation Endpoints (RTR/PPR)
# ============================================================================

@swx_api.route('/deregister/<imsi>', methods=['POST'])
@require_swx_enabled
def deregister_subscriber(imsi):
    """
    Deregister subscriber from non-3GPP access (send RTR).
    
    Args:
        imsi: Subscriber IMSI (path parameter)
        
    Body (JSON, optional):
        reason_code: int (default 0 - PERMANENT_TERMINATION)
        reason_info: str (optional reason text)
        
    Returns:
        JSON result
    """
    try:
        handler = get_swx_handler()
        data = request.get_json() or {}
        
        reason_code = data.get('reason_code', 0)
        reason_info = data.get('reason_info')
        
        success, message = handler.send_rtr(
            imsi,
            reason_code=reason_code,
            reason_info=reason_info
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'imsi': imsi
            })
        else:
            return jsonify({
                'success': False,
                'error': message,
                'imsi': imsi
            }), 404
            
    except Exception as e:
        api_logger.error(f"Error sending RTR: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/push-profile/<imsi>', methods=['POST'])
@require_swx_enabled
def push_profile(imsi):
    """
    Push updated profile to AAA server (send PPR).
    
    Args:
        imsi: Subscriber IMSI (path parameter)
        
    Returns:
        JSON result
    """
    try:
        handler = get_swx_handler()
        
        success, message = handler.send_ppr(imsi)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'imsi': imsi
            })
        else:
            return jsonify({
                'success': False,
                'error': message,
                'imsi': imsi
            }), 404
            
    except Exception as e:
        api_logger.error(f"Error sending PPR: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Status and Info Endpoints
# ============================================================================

@swx_api.route('/status', methods=['GET'])
def get_swx_status():
    """
    Get SWx interface status.
    
    Returns:
        JSON status object
    """
    try:
        handler = get_swx_handler()
        database = get_database()
        
        status = {
            'enabled': handler.enabled if handler else False,
            'config': {}
        }
        
        if handler and handler.enabled:
            status['config'] = {
                'default_apn': handler.default_apn,
                'auth_scheme': handler.auth_scheme,
                'num_auth_vectors': handler.num_auth_vectors,
                'auto_create_subscription': handler.auto_create_subscription
            }
            
            # Get registration counts
            try:
                from lib.models_swx import SWX_REGISTRATION
                
                with database.get_session() as session:
                    total = session.query(SWX_REGISTRATION).count()
                    active = session.query(SWX_REGISTRATION).filter(
                        SWX_REGISTRATION.is_active == True
                    ).count()
                    
                    status['registrations'] = {
                        'total': total,
                        'active': active
                    }
            except Exception as e:
                api_logger.debug(f"Could not get registration counts: {e}")
        
        return jsonify(status)
        
    except Exception as e:
        api_logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500


@swx_api.route('/stats', methods=['GET'])
@require_swx_enabled
def get_swx_stats():
    """
    Get SWx interface statistics from Redis.
    
    Returns:
        JSON statistics object
    """
    try:
        handler = get_swx_handler()
        
        if not handler.redis_store:
            return jsonify({'error': 'Redis not configured'}), 503
        
        stats = {}
        stat_keys = [
            'swx_mar_request_count',
            'swx_mar_success_count',
            'swx_mar_error_count',
            'swx_mar_user_unknown_count',
            'swx_sar_request_count',
            'swx_sar_success_count',
            'swx_sar_error_count',
            'swx_sar_deregistration_count',
            'swx_rtr_sent_count',
            'swx_rtr_error_count',
            'swx_rta_received_count',
            'swx_ppr_sent_count',
            'swx_ppr_error_count',
            'swx_ppa_received_count'
        ]
        
        for key in stat_keys:
            try:
                value = handler.redis_store.get(key)
                stats[key] = int(value) if value else 0
            except:
                stats[key] = 0
        
        return jsonify(stats)
        
    except Exception as e:
        api_logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Blueprint registration helper
# ============================================================================

def register_swx_api(app, swx_handler, database):
    """
    Register SWx API blueprint with Flask app.
    
    Args:
        app: Flask application instance
        swx_handler: SWxHandler instance
        database: PyHSS database module
    """
    app.config['SWX_HANDLER'] = swx_handler
    app.config['DATABASE'] = database
    app.register_blueprint(swx_api)
    api_logger.info("SWx API registered")
