#!/usr/bin/env bash
# ==============================================================================
# Bangladesh AI Shopping Decision Agent - Ubuntu 22.04 Docker Deployment Script
# ==============================================================================
set -e

# Define color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

COMPOSE_CMD="docker compose"

# Function: Fix Docker DNS on Ubuntu 22.04
fix_dns() {
    echo -e "${BLUE}==> Configuring Docker daemon DNS for Ubuntu 22.04...${NC}"
    sudo mkdir -p /etc/docker
    sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "dns": ["8.8.8.8", "1.1.1.1"]
}
EOF
    sudo systemctl restart docker
    echo -e "${GREEN}==> Docker DNS configured and service restarted.${NC}"
}

# Function: Start application
start_app() {
    echo -e "${BLUE}==> Building and starting Shopping Agent container...${NC}"
    $COMPOSE_CMD up -d --build

    echo -e "${BLUE}==> Checking container status...${NC}"
    sleep 3
    $COMPOSE_CMD ps

    SERVER_IP=$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}')
    echo -e "\n${GREEN}===================================================================${NC}"
    echo -e "${GREEN}  Shopping Agent is running!${NC}"
    echo -e "  Web UI: ${BLUE}http://${SERVER_IP}:8501${NC}"
    echo -e "${GREEN}===================================================================${NC}"
}

# Command dispatcher
case "$1" in
    up|"")
        start_app
        ;;
    down)
        $COMPOSE_CMD down
        ;;
    restart)
        $COMPOSE_CMD down
        start_app
        ;;
    logs)
        $COMPOSE_CMD logs -f shopping-agent
        ;;
    status)
        $COMPOSE_CMD ps
        ;;
    update)
        git pull origin main || git pull
        start_app
        ;;
    fix-dns)
        fix_dns
        ;;
    *)
        echo "Usage: $0 {up|down|restart|logs|status|update|fix-dns}"
        exit 1
        ;;
esac
