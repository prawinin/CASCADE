#!/usr/bin/env bash
# =====================================================================
# KINETICKSKETCH AI - WSL 2 AUTO-SETUP UTILITY
# =====================================================================
set -e

echo -e "\e[1;35m=== 🧬 KineticSketch AI WSL 2 Environment Setup ===\e[0m"

# 1. Resolve WSL 2 MTU Issue to prevent SSL decryption failures
echo -e "\e[1;34m[1/5] Adjusting network MTU to 1400 to prevent SSL packet decryption errors...\e[0m"
sudo ip link set dev eth0 mtu 1400 || echo "Warning: Failed to set MTU. Continuing..."

# 2. Add deadsnakes PPA with Noble compatibility if needed
if ! command -v python3.12 &>/dev/null; then
    echo -e "\e[1;34m[2/5] Python 3.12 not found. Setting up deadsnakes PPA...\e[0m"
    sudo apt-get update
    sudo apt-get install -y software-properties-common gpg
    
    # Install curl if not present
    sudo apt-get install -y curl gpg
    
    # Import GPG key in dearmored world-readable format
    sudo curl -sS "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF23C5A2D75C45A89" | gpg --dearmor | sudo tee /usr/share/keyrings/deadsnakes-keyring.gpg > /dev/null
    sudo chmod 644 /usr/share/keyrings/deadsnakes-keyring.gpg
    
    # Write noble sources list
    echo -e "Types: deb\nURIs: https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu\nSuites: noble\nComponents: main\nSigned-By: /usr/share/keyrings/deadsnakes-keyring.gpg" | sudo tee /etc/apt/sources.list.d/deadsnakes.sources
    
    sudo apt-get update
    sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
else
    echo -e "\e[1;32m[2/5] Python 3.12 is already installed.\e[0m"
fi

# 3. Install uv for fast & robust dependency management
if ! command -v uv &>/dev/null && [ ! -f "$HOME/.local/bin/uv" ]; then
    echo -e "\e[1;34m[3/5] Installing uv package manager...\e[0m"
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo -e "\e[1;32m[3/5] uv is already installed.\e[0m"
fi

# Add uv to path for the current script session
export PATH="$HOME/.local/bin:$PATH"

# 4. Recreate virtual environment with Python 3.12
echo -e "\e[1;34m[4/5] Recreating virtual environment (.venv) using Python 3.12...\e[0m"
uv venv --python 3.12 --clear

# 5. Install requirements
echo -e "\e[1;34m[5/5] Installing project dependencies...\e[0m"
uv pip install -r requirements.txt

# 6. Install test dependencies (optional)
if [ -f "requirements-test.txt" ]; then
    echo -e "\e[1;34mInstalling test dependencies...\e[0m"
    uv pip install -r requirements-test.txt
fi

echo -e "\e[1;32m=== Setup Completed Successfully! ===\e[0m"
echo -e "To activate the virtual environment, run:"
echo -e "\e[1;36msource .venv/bin/activate\e[0m"
echo -e "To launch the workspace:"
echo -e "\e[1;36mpython kinetic_sketch.py\e[0m"
