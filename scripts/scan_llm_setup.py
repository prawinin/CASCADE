#!/usr/bin/env python3
"""
KineticSketch — Local LLM & AI Environment Scanner
=====================================================
Scans local system hardware and inspects running/installed local LLM services.
Provides personalized step-by-step installation instructions for PyMOL AI integration.
"""

import sys
import os
import platform
import subprocess
import json
import urllib.request
import urllib.error

def colored(text: str, color_code: str) -> str:
    """Returns ANSI colorized string for terminal output."""
    if sys.stdout.isatty():
        return f"\033[{color_code}m{text}\033[0m"
    return text

GREEN = "32"
YELLOW = "33"
RED = "31"
CYAN = "36"
BOLD = "1"

def print_header(title: str):
    print("\n" + colored("═" * 68, CYAN))
    print(colored(f"  {title}", BOLD))
    print(colored("═" * 68, CYAN))

def check_http_endpoint(url: str, timeout: float = 2.0) -> tuple[bool, dict]:
    """Probes an HTTP endpoint for JSON response."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KineticSketch-Scanner"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data
    except Exception:
        pass
    return False, {}

def get_system_specs() -> dict:
    """Detects CPU, RAM, GPU, and OS capabilities."""
    specs = {
        "os": platform.system(),
        "arch": platform.machine(),
        "release": platform.release(),
        "ram_gb": 0.0,
        "gpu_type": "CPU Only / Integrated",
        "gpu_details": "No dedicated accelerator detected"
    }

    # RAM detection
    try:
        if specs["os"] == "Linux":
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        specs["ram_gb"] = round(kb / (1024 * 1024), 1)
                        break
        elif specs["os"] == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            specs["ram_gb"] = round(int(out) / (1024**3), 1)
        elif specs["os"] == "Windows":
            out = subprocess.check_output(["wmic", "computersystem", "get", "TotalPhysicalMemory"]).decode().split()
            if len(out) > 1:
                specs["ram_gb"] = round(int(out[1]) / (1024**3), 1)
    except Exception:
        specs["ram_gb"] = 8.0  # fallback estimation

    # GPU Detection
    # 1. NVIDIA (nvidia-smi)
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            specs["gpu_type"] = "NVIDIA CUDA"
            specs["gpu_details"] = res.stdout.strip().replace("\n", " | ")
            return specs
    except Exception:
        pass

    # 2. AMD (rocm-smi or lspci)
    try:
        res = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            specs["gpu_type"] = "AMD ROCm"
            specs["gpu_details"] = "AMD Radeon GPU (ROCm driver active)"
            return specs
    except Exception:
        pass

    try:
        res = subprocess.run(["lspci"], capture_output=True, text=True)
        if res.returncode == 0:
            lines = [l for l in res.stdout.split("\n") if "VGA" in l or "3D" in l or "Display" in l]
            if any("Radeon" in l or "AMD" in l or "Advanced Micro Devices" in l for l in lines):
                specs["gpu_type"] = "AMD Radeon"
                specs["gpu_details"] = lines[0] if lines else "AMD GPU"
                return specs
            elif any("NVIDIA" in l for l in lines):
                specs["gpu_type"] = "NVIDIA GPU"
                specs["gpu_details"] = lines[0] if lines else "NVIDIA GPU"
                return specs
    except Exception:
        pass

    # 3. Apple Silicon
    if specs["os"] == "Darwin" and specs["arch"] == "arm64":
        specs["gpu_type"] = "Apple Silicon Metal"
        specs["gpu_details"] = "Unified Memory Metal GPU"

    return specs

def scan_llm_services() -> list[dict]:
    """Scans for active local LLM servers."""
    found = []

    # 1. Ollama (Default KineticSketch engine)
    ok, data = check_http_endpoint("http://localhost:11434/api/tags")
    if ok:
        models = [m.get("name") for m in data.get("models", [])]
        found.append({
            "name": "Ollama",
            "port": 11434,
            "status": "Running (Active)",
            "models": models,
            "recommended": True,
            "desc": "Primary engine supported by KineticSketch PyMOL AI assistant."
        })
    else:
        # Check if installed in PATH
        try:
            res = subprocess.run(["which", "ollama"], capture_output=True, text=True)
            if res.returncode == 0:
                found.append({
                    "name": "Ollama",
                    "port": 11434,
                    "status": "Installed (Not Running)",
                    "models": [],
                    "recommended": True,
                    "desc": "Installed locally but daemon service is offline."
                })
        except Exception:
            pass

    # 2. LM Studio
    ok, data = check_http_endpoint("http://localhost:1234/v1/models")
    if ok:
        models = [m.get("id") for m in data.get("data", [])]
        found.append({
            "name": "LM Studio",
            "port": 1234,
            "status": "Running (Active)",
            "models": models,
            "recommended": False,
            "desc": "OpenAI-compatible server running on port 1234."
        })

    # 3. LocalAI
    ok, data = check_http_endpoint("http://localhost:8080/v1/models")
    if ok:
        found.append({
            "name": "LocalAI",
            "port": 8080,
            "status": "Running (Active)",
            "models": [m.get("id") for m in data.get("data", [])],
            "recommended": False,
            "desc": "LocalAI container active on port 8080."
        })

    # 4. Text Generation WebUI (Oobabooga)
    ok, _ = check_http_endpoint("http://localhost:7860")
    if ok:
        found.append({
            "name": "Text Generation WebUI (Oobabooga)",
            "port": 7860,
            "status": "Running (Active)",
            "models": [],
            "recommended": False,
            "desc": "WebUI instance listening on port 7860."
        })

    # 5. KoboldCPP
    ok, _ = check_http_endpoint("http://localhost:5001/api/v1/model")
    if ok:
        found.append({
            "name": "KoboldCPP",
            "port": 5001,
            "status": "Running (Active)",
            "models": [],
            "recommended": False,
            "desc": "KoboldCPP server active on port 5001."
        })

    # 6. Jan.ai
    ok, data = check_http_endpoint("http://localhost:1337/v1/models")
    if ok:
        found.append({
            "name": "Jan.ai",
            "port": 1337,
            "status": "Running (Active)",
            "models": [m.get("id") for m in data.get("data", [])],
            "recommended": False,
            "desc": "Jan desktop app active on port 1337."
        })

    return found

def main():
    print_header("KineticSketch — Local LLM & AI Environment Scanner")

    # Step 1: System Specs
    specs = get_system_specs()
    print(colored("► System Hardware Profile:", BOLD))
    print(f"  • Operating System: {specs['os']} ({specs['arch']} / {specs['release']})")
    print(f"  • System Memory:   {specs['ram_gb']} GB RAM")
    print(f"  • Graphics/Compute: {specs['gpu_type']} — {specs['gpu_details']}")

    # Step 2: Scan LLMs
    print_header("Scanning Local LLM Engines & Services")
    services = scan_llm_services()

    ollama_active = False
    ollama_has_qwen = False

    if not services:
        print(colored("  ⚠ No active local LLM servers detected on standard ports.", YELLOW))
    else:
        for s in services:
            badge = colored(" [RECOMMENDED] ", GREEN) if s["recommended"] else ""
            status_color = GREEN if "Running" in s["status"] else YELLOW
            print(f"\n  • {colored(s['name'], BOLD)}{badge}")
            print(f"    Status: {colored(s['status'], status_color)}")
            print(f"    Port:   {s['port']}")
            print(f"    Note:   {s['desc']}")

            if s['models']:
                print(f"    Models: {', '.join(s['models'][:5])}")
                if any("qwen" in m.lower() or "llama" in m.lower() for m in s['models']):
                    ollama_has_qwen = True

            if s['name'] == "Ollama" and "Running" in s['status']:
                ollama_active = True

    # Step 3: Installation & Configuration Guidance
    print_header("KineticSketch PyMOL AI Setup Guidance")

    if ollama_active and ollama_has_qwen:
        print(colored("  ✓ EXCELLENT SETUP DETECTED!", GREEN))
        print("  Ollama is running with compatible coding models (Qwen2.5-Coder or Llama3).")
        print("  KineticSketch will automatically connect to Ollama on http://localhost:11434.")
        print("\n  To test in KineticSketch:")
        print("  Switch to '3D View' tab → type in PyMOL AI box: 'show surface, color red'")

    elif ollama_active:
        print(colored("  ✓ Ollama is running, but no recommended code/PyMOL model was found.", YELLOW))
        print("\n  Run the following command to download the recommended lightweight model:")
        print(colored("    ollama pull qwen2.5-coder:7b", CYAN))
        print("  Or for low VRAM systems (< 6GB):")
        print(colored("    ollama pull llama3.2:3b", CYAN))

    else:
        print(colored("  ► Step-by-Step Installation Instructions for your system:", BOLD))
        print(f"  (System: {specs['os']} | RAM: {specs['ram_gb']} GB | GPU: {specs['gpu_type']})\n")

        if specs['os'] == "Linux":
            print("  1. Install Ollama:")
            print(colored("     curl -fsSL https://ollama.com/install.sh | sh", CYAN))
            print("  2. Start Ollama daemon:")
            print(colored("     ollama serve &", CYAN))
            print("  3. Pull the PyMOL AI model:")
            print(colored("     ollama pull qwen2.5-coder:7b", CYAN))

        elif specs['os'] == "Darwin":
            print("  1. Download Ollama for macOS:")
            print(colored("     https://ollama.com/download/Ollama-darwin.zip", CYAN))
            print("  2. Or install via Homebrew:")
            print(colored("     brew install ollama && brew services start ollama", CYAN))
            print("  3. Pull the model:")
            print(colored("     ollama pull qwen2.5-coder:7b", CYAN))

        elif specs['os'] == "Windows":
            print("  1. Download Ollama Windows Installer:")
            print(colored("     https://ollama.com/download/OllamaSetup.exe", CYAN))
            print("  2. Open Command Prompt / PowerShell and pull the model:")
            print(colored("     ollama pull qwen2.5-coder:7b", CYAN))

    print("\n" + colored("═" * 68, CYAN) + "\n")

if __name__ == "__main__":
    main()
