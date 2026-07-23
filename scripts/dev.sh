#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# PR Guardian - Local Development Script
# Levanta todos los servicios necesarios para desarrollo local
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[pr-guardian]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check prerequisites
check_deps() {
    log "Checking prerequisites..."

    command -v uv &>/dev/null || error "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    command -v redis-cli &>/dev/null || error "Redis not found. Install: brew install redis"
    command -v node &>/dev/null || error "Node.js not found. Install: brew install node"

    if ! redis-cli ping &>/dev/null; then
        warn "Redis not running. Starting..."
        brew services start redis 2>/dev/null || redis-server --daemonize yes
        sleep 1
    fi
    success "All prerequisites met"
}

# Check .env file
check_env() {
    if [ ! -f .env ]; then
        error ".env file not found. Run: cp .env.example .env and fill in your credentials"
    fi

    # Check critical vars
    source .env 2>/dev/null
    [ -z "${GITHUB_WEBHOOK_SECRET:-}" ] && error "GITHUB_WEBHOOK_SECRET not set in .env"
    [ -z "${GITHUB_TOKEN:-}" ] && error "GITHUB_TOKEN not set in .env"
    [ -z "${LLM_API_KEY:-}" ] && error "LLM_API_KEY not set in .env"

    success "Environment configured"
}

# Install dependencies
install_deps() {
    log "Syncing Python dependencies..."
    uv sync --quiet
    success "Python dependencies installed"

    if [ -f dashboard/package.json ]; then
        log "Installing dashboard dependencies..."
        cd dashboard && npm install --silent && cd ..
        success "Dashboard dependencies installed"
    fi
}

# Create data dir
setup_data() {
    mkdir -p data
}

# Kill background processes on exit
PIDS=()
cleanup() {
    log "Shutting down services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    success "All services stopped"
}
trap cleanup EXIT

# Start services
start_services() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🛡️  PR Guardian - Starting Local Services${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Webhook Handler
    log "Starting Webhook Handler on :8000..."
    uv run uvicorn github_integration.webhook_handler:app \
        --host 0.0.0.0 --port 8000 --reload \
        --app-dir . \
        2>&1 | sed 's/^/  [webhook] /' &
    PIDS+=($!)
    sleep 2

    # Celery Worker
    log "Starting Celery Worker..."
    uv run celery -A worker.celery_app worker \
        --loglevel=info --concurrency=2 \
        2>&1 | sed 's/^/  [worker]  /' &
    PIDS+=($!)
    sleep 2

    # MCP Server
    log "Starting MCP Server on :8080..."
    uv run python github-integration/server.py \
        2>&1 | sed 's/^/  [mcp]     /' &
    PIDS+=($!)
    sleep 1

    echo ""
    success "All services running!"
    echo ""
    echo -e "  ${GREEN}Webhook:${NC}  http://localhost:8000"
    echo -e "  ${GREEN}MCP:${NC}      http://localhost:8080"
    echo -e "  ${GREEN}Redis:${NC}    localhost:6379"
    echo ""
    echo -e "  ${YELLOW}Tip:${NC} Use ngrok to expose webhook: ngrok http 8000"
    echo -e "  ${YELLOW}Tip:${NC} Press Ctrl+C to stop all services"
    echo ""

    # Wait for any process to exit
    wait
}

# Main
main() {
    cd "$(dirname "$0")/.."
    check_deps
    check_env
    install_deps
    setup_data
    start_services
}

main
