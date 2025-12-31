#!/bin/bash
#
# PyHSS SWx Addon Installation Script
# 
# This script installs the SWx addon files into an existing PyHSS installation.
#
# Usage:
#   ./install.sh /opt/pyhss
#
# Author: PyHSS Community
# License: AGPL-3.0
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default PyHSS path
PYHSS_PATH="${1:-/opt/pyhss}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  PyHSS SWx Addon Installer${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if PyHSS path exists
if [ ! -d "$PYHSS_PATH" ]; then
    echo -e "${RED}Error: PyHSS path not found: $PYHSS_PATH${NC}"
    echo "Usage: $0 /path/to/pyhss"
    exit 1
fi

# Check if this looks like a PyHSS installation
if [ ! -f "$PYHSS_PATH/hssService.py" ]; then
    echo -e "${RED}Error: hssService.py not found in $PYHSS_PATH${NC}"
    echo "This doesn't appear to be a PyHSS installation."
    exit 1
fi

echo -e "${YELLOW}Installing to: $PYHSS_PATH${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create backup directory
BACKUP_DIR="$PYHSS_PATH/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo -e "${YELLOW}Backup directory: $BACKUP_DIR${NC}"

# Backup existing files if they exist
backup_file() {
    local file="$1"
    if [ -f "$PYHSS_PATH/$file" ]; then
        mkdir -p "$BACKUP_DIR/$(dirname $file)"
        cp "$PYHSS_PATH/$file" "$BACKUP_DIR/$file"
        echo "  Backed up: $file"
    fi
}

echo ""
echo "Backing up existing files..."
backup_file "lib/diameter_swx.py"
backup_file "lib/models_swx.py"
backup_file "services/hss_swx_handler.py"
backup_file "api/api_swx.py"
backup_file "swx_init.py"

# Create directories if they don't exist
echo ""
echo "Creating directories..."
mkdir -p "$PYHSS_PATH/lib"
mkdir -p "$PYHSS_PATH/services"
mkdir -p "$PYHSS_PATH/api"
mkdir -p "$PYHSS_PATH/migrations/versions"

# Copy files
echo ""
echo "Installing SWx addon files..."

copy_file() {
    local src="$1"
    local dst="$2"
    cp "$SCRIPT_DIR/$src" "$PYHSS_PATH/$dst"
    echo -e "  ${GREEN}✓${NC} $dst"
}

# Core library files
copy_file "lib/diameter_swx.py" "lib/diameter_swx.py"
copy_file "lib/models_swx.py" "lib/models_swx.py"

# Service handler
copy_file "services/hss_swx_handler.py" "services/hss_swx_handler.py"

# API endpoints
copy_file "api/api_swx.py" "api/api_swx.py"

# Integration module
copy_file "swx_init.py" "swx_init.py"

# Database migration
copy_file "migrations/swx_001_add_swx_tables.py" "migrations/versions/swx_001_add_swx_tables.py"

# Configuration template
copy_file "config_swx.yaml" "config_swx.yaml.example"

# Documentation
mkdir -p "$PYHSS_PATH/docs/swx"
copy_file "docs/README.md" "docs/swx/README.md"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Add SWx configuration to config.yaml:"
echo "   cat $PYHSS_PATH/config_swx.yaml.example >> $PYHSS_PATH/config.yaml"
echo ""
echo "2. Edit config.yaml and set 'swx.enabled: true'"
echo ""
echo "3. Run database migrations:"
echo "   cd $PYHSS_PATH && alembic upgrade head"
echo ""
echo "4. Modify hssService.py to add SWx routing (see docs/swx/README.md)"
echo ""
echo "5. Restart PyHSS services:"
echo "   systemctl restart pyhss-diameter pyhss-hss pyhss-api"
echo ""
echo -e "${YELLOW}Backup saved to: $BACKUP_DIR${NC}"
echo ""
echo "For more information, see: $PYHSS_PATH/docs/swx/README.md"
