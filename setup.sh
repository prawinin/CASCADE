#!/usr/bin/env bash
# CASCADE — First-run setup
# Downloads the required data and model files from GitHub Releases,
# then prints the command to start the application.
set -euo pipefail

RELEASE_BASE="https://github.com/prawinin/CASCADE/releases/download/v1.0.0"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[setup]${NC} $*"; }

check_cmd() {
    command -v "$1" &>/dev/null || { echo "Error: '$1' is required but not installed."; exit 1; }
}

download() {
    local url="$1" dest="$2"
    if [[ -f "$dest" ]]; then
        info "Already exists: $(basename "$dest") — skipping."
        return
    fi
    info "Downloading $(basename "$dest") ..."
    mkdir -p "$(dirname "$dest")"
    curl -fL --progress-bar "$url" -o "$dest"
    info "Saved: $dest"
}

check_cmd curl
check_cmd docker

info "CASCADE setup starting..."

download "$RELEASE_BASE/drug_database.sqlite"  "$REPO_ROOT/data/drug_database.sqlite"
download "$RELEASE_BASE/drug_fingerprints.npz" "$REPO_ROOT/data/drug_fingerprints.npz"
download "$RELEASE_BASE/mdrepo_predictor.pt"   "$REPO_ROOT/app/models/mdrepo_predictor.pt"

info "All data files ready."
echo ""
info "Run the app with:"
echo "    python compose_up.py"
echo ""
warn "Or directly with Docker Compose:"
echo "    docker compose up"
echo ""
