"""Add SWx interface tables

Revision ID: swx_001
Revises: 
Create Date: 2024-01-01

This migration adds tables for SWx (non-3GPP) interface support:
- swx_registration: Tracks AAA server registrations
- non_3gpp_subscription: Subscriber non-3GPP access settings
- swx_apn_configuration: APN-specific settings for non-3GPP
- swx_emergency_info: Emergency services configuration
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, mysql

# revision identifiers, used by Alembic.
revision = 'swx_001'
down_revision = None  # Update this to your latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Create SWx interface tables."""
    
    # swx_registration table
    op.create_table(
        'swx_registration',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('subscriber_id', sa.Integer(), sa.ForeignKey('subscriber.subscriber_id'), nullable=False),
        sa.Column('imsi', sa.String(15), nullable=False, index=True),
        sa.Column('aaa_server_name', sa.String(255), nullable=False),
        sa.Column('aaa_realm', sa.String(255), nullable=False),
        sa.Column('aaa_peer', sa.String(255), nullable=True),
        sa.Column('registration_time', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('last_update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('access_type', sa.String(50), default='UNTRUSTED_WLAN'),
        sa.Column('rat_type', sa.String(20), nullable=True),
        sa.Column('pgw_address', sa.String(50), nullable=True),
        sa.Column('epdg_address', sa.String(50), nullable=True),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('deregistration_reason', sa.Integer(), nullable=True),
        sa.Column('emergency_services_enabled', sa.Boolean(), default=False)
    )
    
    # Create indexes for swx_registration
    op.create_index('ix_swx_registration_subscriber_id', 'swx_registration', ['subscriber_id'])
    op.create_index('ix_swx_registration_imsi_active', 'swx_registration', ['imsi', 'is_active'])
    
    # non_3gpp_subscription table
    op.create_table(
        'non_3gpp_subscription',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('subscriber_id', sa.Integer(), sa.ForeignKey('subscriber.subscriber_id'), nullable=False, unique=True),
        sa.Column('non_3gpp_ip_access', sa.Integer(), default=0, nullable=False),
        sa.Column('non_3gpp_ip_access_apn', sa.Integer(), default=0, nullable=False),
        sa.Column('an_trusted', sa.Integer(), default=1, nullable=False),
        sa.Column('max_requested_bandwidth_ul', sa.BigInteger(), default=100000000),
        sa.Column('max_requested_bandwidth_dl', sa.BigInteger(), default=100000000),
        sa.Column('auth_scheme', sa.String(50), default='EAP-AKA'),
        sa.Column('num_auth_vectors', sa.Integer(), default=1),
        sa.Column('allowed_apns', sa.Text(), nullable=True),
        sa.Column('default_apn', sa.String(100), default='ims'),
        sa.Column('emergency_services_allowed', sa.Boolean(), default=True),
        sa.Column('emergency_apn', sa.String(100), default='sos'),
        sa.Column('wlan_offload_enabled', sa.Boolean(), default=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )
    
    # Create index for non_3gpp_subscription
    op.create_index('ix_non_3gpp_subscription_subscriber_id', 'non_3gpp_subscription', ['subscriber_id'])
    
    # swx_apn_configuration table
    op.create_table(
        'swx_apn_configuration',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('non_3gpp_subscription_id', sa.Integer(), sa.ForeignKey('non_3gpp_subscription.id'), nullable=False),
        sa.Column('context_identifier', sa.Integer(), default=1, nullable=False),
        sa.Column('apn', sa.String(100), nullable=False),
        sa.Column('pdn_type', sa.Integer(), default=0, nullable=False),
        sa.Column('vplmn_dynamic_address_allowed', sa.Integer(), default=1),
        sa.Column('qos_class_identifier', sa.Integer(), default=9),
        sa.Column('priority_level', sa.Integer(), default=8),
        sa.Column('preemption_capability', sa.Integer(), default=1),
        sa.Column('preemption_vulnerability', sa.Integer(), default=0),
        sa.Column('max_requested_bandwidth_ul', sa.BigInteger(), default=50000000),
        sa.Column('max_requested_bandwidth_dl', sa.BigInteger(), default=100000000),
        sa.Column('pgw_allocation_type', sa.Integer(), default=1),
        sa.Column('pgw_address', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False)
    )
    
    # Create index for swx_apn_configuration
    op.create_index('ix_swx_apn_config_subscription_id', 'swx_apn_configuration', ['non_3gpp_subscription_id'])
    
    # swx_emergency_info table
    op.create_table(
        'swx_emergency_info',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('subscriber_id', sa.Integer(), sa.ForeignKey('subscriber.subscriber_id'), nullable=True),
        sa.Column('emergency_services_type', sa.Integer(), default=1),
        sa.Column('emergency_apn', sa.String(100), default='sos'),
        sa.Column('lrf_address', sa.String(255), nullable=True),
        sa.Column('emergency_numbers', sa.Text(), nullable=True),
        sa.Column('ims_voice_over_ps_sessions_supported', sa.Boolean(), default=True),
        sa.Column('emergency_pdn_type', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False)
    )
    
    # Create index for swx_emergency_info
    op.create_index('ix_swx_emergency_info_subscriber_id', 'swx_emergency_info', ['subscriber_id'])
    
    print("SWx tables created successfully")


def downgrade():
    """Remove SWx interface tables."""
    
    # Drop indexes first
    op.drop_index('ix_swx_emergency_info_subscriber_id', table_name='swx_emergency_info')
    op.drop_index('ix_swx_apn_config_subscription_id', table_name='swx_apn_configuration')
    op.drop_index('ix_non_3gpp_subscription_subscriber_id', table_name='non_3gpp_subscription')
    op.drop_index('ix_swx_registration_imsi_active', table_name='swx_registration')
    op.drop_index('ix_swx_registration_subscriber_id', table_name='swx_registration')
    
    # Drop tables
    op.drop_table('swx_emergency_info')
    op.drop_table('swx_apn_configuration')
    op.drop_table('non_3gpp_subscription')
    op.drop_table('swx_registration')
    
    print("SWx tables removed successfully")


# ============================================================================
# Raw SQL for manual execution (if not using Alembic)
# ============================================================================

CREATE_TABLES_SQL = """
-- SWx Registration Table
CREATE TABLE IF NOT EXISTS swx_registration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL,
    imsi VARCHAR(15) NOT NULL,
    aaa_server_name VARCHAR(255) NOT NULL,
    aaa_realm VARCHAR(255) NOT NULL,
    aaa_peer VARCHAR(255),
    registration_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_update_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    access_type VARCHAR(50) DEFAULT 'UNTRUSTED_WLAN',
    rat_type VARCHAR(20),
    pgw_address VARCHAR(50),
    epdg_address VARCHAR(50),
    session_id VARCHAR(255),
    is_active BOOLEAN DEFAULT 1,
    deregistration_reason INTEGER,
    emergency_services_enabled BOOLEAN DEFAULT 0,
    FOREIGN KEY (subscriber_id) REFERENCES subscriber(subscriber_id)
);

CREATE INDEX IF NOT EXISTS ix_swx_registration_imsi ON swx_registration(imsi);
CREATE INDEX IF NOT EXISTS ix_swx_registration_subscriber_id ON swx_registration(subscriber_id);

-- Non-3GPP Subscription Table
CREATE TABLE IF NOT EXISTS non_3gpp_subscription (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL UNIQUE,
    non_3gpp_ip_access INTEGER DEFAULT 0,
    non_3gpp_ip_access_apn INTEGER DEFAULT 0,
    an_trusted INTEGER DEFAULT 1,
    max_requested_bandwidth_ul BIGINT DEFAULT 100000000,
    max_requested_bandwidth_dl BIGINT DEFAULT 100000000,
    auth_scheme VARCHAR(50) DEFAULT 'EAP-AKA',
    num_auth_vectors INTEGER DEFAULT 1,
    allowed_apns TEXT,
    default_apn VARCHAR(100) DEFAULT 'ims',
    emergency_services_allowed BOOLEAN DEFAULT 1,
    emergency_apn VARCHAR(100) DEFAULT 'sos',
    wlan_offload_enabled BOOLEAN DEFAULT 1,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscriber_id) REFERENCES subscriber(subscriber_id)
);

CREATE INDEX IF NOT EXISTS ix_non_3gpp_subscription_subscriber_id ON non_3gpp_subscription(subscriber_id);

-- SWx APN Configuration Table
CREATE TABLE IF NOT EXISTS swx_apn_configuration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    non_3gpp_subscription_id INTEGER NOT NULL,
    context_identifier INTEGER DEFAULT 1,
    apn VARCHAR(100) NOT NULL,
    pdn_type INTEGER DEFAULT 0,
    vplmn_dynamic_address_allowed INTEGER DEFAULT 1,
    qos_class_identifier INTEGER DEFAULT 9,
    priority_level INTEGER DEFAULT 8,
    preemption_capability INTEGER DEFAULT 1,
    preemption_vulnerability INTEGER DEFAULT 0,
    max_requested_bandwidth_ul BIGINT DEFAULT 50000000,
    max_requested_bandwidth_dl BIGINT DEFAULT 100000000,
    pgw_allocation_type INTEGER DEFAULT 1,
    pgw_address VARCHAR(50),
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (non_3gpp_subscription_id) REFERENCES non_3gpp_subscription(id)
);

CREATE INDEX IF NOT EXISTS ix_swx_apn_config_subscription_id ON swx_apn_configuration(non_3gpp_subscription_id);

-- SWx Emergency Info Table
CREATE TABLE IF NOT EXISTS swx_emergency_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER,
    emergency_services_type INTEGER DEFAULT 1,
    emergency_apn VARCHAR(100) DEFAULT 'sos',
    lrf_address VARCHAR(255),
    emergency_numbers TEXT,
    ims_voice_over_ps_sessions_supported BOOLEAN DEFAULT 1,
    emergency_pdn_type INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (subscriber_id) REFERENCES subscriber(subscriber_id)
);

CREATE INDEX IF NOT EXISTS ix_swx_emergency_info_subscriber_id ON swx_emergency_info(subscriber_id);
"""

DROP_TABLES_SQL = """
DROP TABLE IF EXISTS swx_emergency_info;
DROP TABLE IF EXISTS swx_apn_configuration;
DROP TABLE IF EXISTS non_3gpp_subscription;
DROP TABLE IF EXISTS swx_registration;
"""
