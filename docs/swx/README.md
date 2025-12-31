# PyHSS SWx Interface Addon

## Overview

This addon implements the **3GPP SWx Diameter interface** for PyHSS, enabling support for non-3GPP access authentication. This is specifically designed to work with **osmo-epdg** for WiFi Calling (VoWiFi) functionality.

### What is SWx?

The SWx interface (defined in 3GPP TS 29.273) connects the **3GPP AAA Server** to the **HSS** for non-3GPP access networks. When a subscriber connects via WiFi (through an ePDG), the AAA server uses SWx to:

1. **Authenticate** the subscriber (MAR/MAA - get EAP-AKA vectors)
2. **Register** the AAA server and retrieve subscriber profile (SAR/SAA)
3. **Deregister** the subscriber (RTR/RTA - HSS initiated)
4. **Push profile updates** (PPR/PPA - HSS initiated)

```
┌─────────┐     SWu       ┌─────────┐     SWm      ┌─────────┐      SWx       ┌─────────┐
│   UE    │──────────────▶│  ePDG   │─────────────▶│   AAA   │───────────────▶│   HSS   │
│ (WiFi)  │  IKEv2/EAP    │         │   Diameter   │ Server  │    Diameter    │ (PyHSS) │
└─────────┘               └─────────┘              └─────────┘                └─────────┘
                                                        │
                                                        │ S6b
                                                        ▼
                                                   ┌─────────┐
                                                   │   PGW   │
                                                   └─────────┘
```

## Features

- **Full SWx Protocol Support**
  - MAR/MAA (303) - Multimedia Authentication
  - SAR/SAA (301) - Server Assignment  
  - RTR/RTA (304) - Registration Termination
  - PPR/PPA (305) - Push Profile

- **EAP-AKA Authentication**
  - EAP-AKA and EAP-AKA' support
  - Multiple authentication vector generation
  - Uses existing PyHSS AuC for key material

- **Non-3GPP Subscription Management**
  - Per-subscriber non-3GPP settings
  - APN-specific configurations for non-3GPP
  - Trusted/Untrusted access network support

- **REST API**
  - Full CRUD for registrations and subscriptions
  - RTR/PPR operations via API
  - Statistics and monitoring

- **osmo-epdg Integration**
  - Tested with Osmocom ePDG
  - Compatible with VoWiFi/WiFi Calling flows

## Installation

### 1. Copy Addon Files

```bash
cd /opt/pyhss

# Copy library files
cp -r pyhss_swx_addon/lib/diameter_swx.py lib/
cp -r pyhss_swx_addon/lib/models_swx.py lib/

# Copy service handler
cp -r pyhss_swx_addon/services/hss_swx_handler.py services/

# Copy API endpoints
cp -r pyhss_swx_addon/api/api_swx.py api/

# Copy integration module
cp pyhss_swx_addon/swx_init.py .

# Copy migrations
cp -r pyhss_swx_addon/migrations/swx_001_add_swx_tables.py migrations/versions/
```

### 2. Update Configuration

Add the SWx section to your `config.yaml`:

```yaml
swx:
  enabled: true
  application_id: 16777265
  default_apn: "ims"
  auth_scheme: "EAP-AKA"
  num_auth_vectors: 1
  auto_create_non3gpp_subscription: true
```

### 3. Run Database Migrations

```bash
# Using Alembic
alembic upgrade head

# Or manually create tables
python -c "
from swx_init import create_swx_tables
import database
import yaml

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

create_swx_tables(database, config)
"
```

### 4. Update hssService.py

Add SWx initialization to `hssService.py`:

```python
# Near the top with other imports
from swx_init import init_swx, is_swx_message, SWX_APPLICATION_ID

# After initializing diameter and database
swx_handler = init_swx(
    diameter_instance=diameter,
    database_instance=database,
    yaml_config=yaml_config,
    redis_store=redis_store
)

# In the message processing loop, add SWx routing:
def process_diameter_request(packet_vars, avps):
    app_id = packet_vars.get('ApplicationId')
    
    # Route SWx messages
    if app_id == SWX_APPLICATION_ID and swx_handler:
        from services.hss_swx_handler import process_swx_request
        return process_swx_request(swx_handler, packet_vars, avps)
    
    # ... existing processing ...
```

### 5. Update apiService.py

Register SWx API endpoints:

```python
from api.api_swx import register_swx_api

# After creating Flask app
if yaml_config.get('swx', {}).get('enabled', False):
    from swx_init import init_swx
    swx_handler = init_swx(diameter, database, yaml_config, redis_store)
    if swx_handler:
        register_swx_api(app, swx_handler, database)
```

### 6. Restart Services

```bash
systemctl restart pyhss-diameter
systemctl restart pyhss-hss
systemctl restart pyhss-api
```

## osmo-epdg Configuration

Configure osmo-epdg to connect to PyHSS:

```erlang
%% osmo-epdg.config

%% Diameter SWx connection
{diameter_remote_ip, "10.0.1.100"}.     % PyHSS IP
{diameter_remote_port, 3868}.
{diameter_proto, sctp}.
{origin_host, "epdg.example.com"}.
{origin_realm, "example.com"}.

%% SWx Application
{swx_application_id, 16777265}.
```

## API Reference

### Status & Monitoring

```bash
# Get SWx status
curl http://localhost:8080/swx/status

# Get statistics
curl http://localhost:8080/swx/stats
```

### Registrations

```bash
# List active registrations
curl http://localhost:8080/swx/registrations

# Get registration for IMSI
curl http://localhost:8080/swx/registration/001010000000001

# Deregister subscriber (sends RTR)
curl -X DELETE http://localhost:8080/swx/registration/001010000000001
```

### Non-3GPP Subscriptions

```bash
# Get subscription
curl http://localhost:8080/swx/subscription/1

# Create/update subscription
curl -X PUT http://localhost:8080/swx/subscription/1 \
  -H "Content-Type: application/json" \
  -d '{
    "non_3gpp_ip_access": 0,
    "an_trusted": 1,
    "default_apn": "ims",
    "max_requested_bandwidth_ul": 100000000,
    "max_requested_bandwidth_dl": 100000000
  }'

# Add APN configuration
curl -X POST http://localhost:8080/swx/subscription/1/apn \
  -H "Content-Type: application/json" \
  -d '{
    "apn": "ims",
    "pdn_type": 0,
    "qos_class_identifier": 5
  }'
```

### Operations

```bash
# Send RTR to deregister
curl -X POST http://localhost:8080/swx/deregister/001010000000001 \
  -H "Content-Type: application/json" \
  -d '{"reason_code": 0}'

# Push profile update
curl -X POST http://localhost:8080/swx/push-profile/001010000000001
```

## Database Schema

### swx_registration
Tracks active non-3GPP registrations:
- `imsi` - Subscriber IMSI
- `aaa_server_name` - AAA server Origin-Host
- `aaa_realm` - AAA server realm
- `access_type` - WLAN, TRUSTED_WLAN, UNTRUSTED_WLAN
- `is_active` - Active registration flag

### non_3gpp_subscription
Per-subscriber non-3GPP settings:
- `subscriber_id` - Link to subscriber table
- `non_3gpp_ip_access` - 0=allowed, 1=barred
- `an_trusted` - 0=trusted, 1=untrusted
- `auth_scheme` - EAP-AKA or EAP-AKA'
- `default_apn` - Default APN for non-3GPP

### swx_apn_configuration
APN-specific settings for non-3GPP:
- `apn` - APN name
- `pdn_type` - IPv4/IPv6/IPv4v6
- `qos_class_identifier` - QCI value
- AMBR settings

## VoWiFi Call Flow

```
UE                    ePDG              AAA/osmo-epdg         PyHSS (SWx)
│                      │                      │                    │
│─── IKE_SA_INIT ─────▶│                      │                    │
│◀── IKE_SA_INIT ─────│                      │                    │
│                      │                      │                    │
│─── IKE_AUTH(EAP) ───▶│                      │                    │
│                      │─── DER (SWm) ───────▶│                    │
│                      │                      │──── MAR ──────────▶│
│                      │                      │                    │ Generate EAP-AKA vectors
│                      │                      │◀─── MAA ───────────│ (RAND, AUTN, XRES, CK, IK)
│                      │◀── DEA (EAP-AKA) ────│                    │
│◀── EAP-Challenge ───│                      │                    │
│                      │                      │                    │
│─── EAP-Response ────▶│                      │                    │
│                      │─── DER ─────────────▶│                    │
│                      │◀── DEA (Success) ────│                    │
│                      │                      │──── SAR ──────────▶│
│                      │                      │                    │ Store AAA registration
│                      │                      │◀─── SAA ───────────│ Return subscriber profile
│◀── IKE_AUTH OK ─────│                      │                    │
│                      │                      │                    │
│═══ IPsec Tunnel ════│                      │                    │
│                      │═══ GTP-U to PGW ════│                    │
│                      │                      │                    │
│─── IMS Register ────▶│───────────────────────────────────────────▶│ (via P-CSCF/S-CSCF)
```

## Troubleshooting

### Enable Debug Logging

```yaml
swx:
  log_level: "DEBUG"
```

### Common Issues

**MAR fails with USER_UNKNOWN**
- Verify subscriber exists in AuC table
- Check IMSI format in User-Name AVP
- Enable debug logging to see extracted IMSI

**SAR fails with NO_APN_SUBSCRIPTION**
- Create non_3gpp_subscription for subscriber
- Or enable `auto_create_non3gpp_subscription: true`

**Connection refused from ePDG**
- Verify PyHSS Diameter port is open (3868)
- Check Origin-Realm matches between peers
- Verify SCTP is enabled if using SCTP transport

**Authentication fails**
- Verify Ki/OPc in AuC table match SIM
- Check AMF value (should be 8000 for EPS)
- Compare vectors with expected values

### Wireshark Filtering

```
# Filter SWx messages
diameter.applicationId == 16777265

# Filter by command
diameter.cmd.code == 303  # MAR/MAA
diameter.cmd.code == 301  # SAR/SAA
```

## References

- [3GPP TS 29.273](https://www.3gpp.org/ftp/Specs/archive/29_series/29.273/) - EPS AAA Interfaces
- [3GPP TS 29.229](https://www.3gpp.org/ftp/Specs/archive/29_series/29.229/) - Cx/Dx Interface
- [3GPP TS 33.402](https://www.3gpp.org/ftp/Specs/archive/33_series/33.402/) - Non-3GPP Security
- [RFC 5448](https://datatracker.ietf.org/doc/html/rfc5448) - EAP-AKA'
- [osmo-epdg](https://osmocom.org/projects/osmo-epdg) - Osmocom ePDG
- [Open5GS HSS](https://github.com/open5gs/open5gs) - Reference implementation

## License

AGPL-3.0 - Same as PyHSS

## Contributing

Contributions welcome! Please submit issues and PRs to the PyHSS repository.
