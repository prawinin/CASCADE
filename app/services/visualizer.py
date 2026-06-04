import logging
import subprocess
import requests
from typing import Optional

logger = logging.getLogger("KineticSketch.Visualizer")

import sys
import os
# Allow relative importing of config module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import get_config

config = get_config()

# Global reference to running PyMOL subprocess
pymol_process: Optional[subprocess.Popen] = None

# Request timeout constants (loaded dynamically from central config)
OLLAMA_TIMEOUT = float(config.OLLAMA_TIMEOUT)
PYMOL_LISTEN_TIMEOUT = float(config.PYMOL_LISTEN_TIMEOUT)

def get_pymol_process() -> Optional[subprocess.Popen]:
    """
    Retrieves or spawns the local PyMOL visualizer pipeline.
    
    Runs 'pymol -p' to listen to Python commands via stdin.
    Returns None if PyMOL is not available or fails to spawn.
    
    Returns:
        PyMOL subprocess.Popen object or None if unavailable
    """
    global pymol_process
    if not config.PYMOL_ENABLED:
        logger.info("PyMOL integration is disabled by configuration.")
        return None

    if pymol_process is None or pymol_process.poll() is not None:
        try:
            logger.info("Initializing non-blocking subprocess PyMOL listener...")
            # Spawning visualizer in listening mode
            pymol_process = subprocess.Popen(
                ["pymol", "-p"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            logger.info("Local PyMOL subprocess successfully launched.")
        except Exception as e:
            logger.warning(f"Unable to launch local PyMOL visualizer process (pymol -p): {e}")
            pymol_process = None
    
    return pymol_process


def fallback_pymol_mapper(prompt: str) -> str:
    """
    Double-insurance local translation dictionary.
    
    Invoked if Ollama server is offline or model is not loaded.
    Translates standard molecular instructions directly to PyMOL APIs.
    
    Args:
        prompt: User visualization request in natural language
    
    Returns:
        String of PyMOL commands, one per line
    """
    prompt_l = prompt.lower()
    commands = []
    
    # Analyze commands
    if "load" in prompt_l or "open" in prompt_l:
        commands.append("load molecule.sdf")
    if "stick" in prompt_l or "wire" in prompt_l:
        commands.append("show sticks")
        commands.append("hide lines")
    if "sphere" in prompt_l or "ball" in prompt_l:
        commands.append("show spheres")
    if "cartoon" in prompt_l or "ribbon" in prompt_l:
        commands.append("show cartoon")
    if "surface" in prompt_l:
        commands.append("show surface")
    if "color" in prompt_l:
        colors = ["red", "green", "blue", "yellow", "cyan", "magenta", "orange", "marine", "pink"]
        selected_color = "cyan"
        for col in colors:
            if col in prompt_l:
                selected_color = col
                break
        commands.append(f"color {selected_color}")
    if "zoom" in prompt_l or "center" in prompt_l:
        commands.append("zoom")
    if "rotate" in prompt_l or "turn" in prompt_l:
        commands.append("turn y, 90")
    if "bg" in prompt_l or "background" in prompt_l:
        if "white" in prompt_l: 
            commands.append("bg_color white")
        else: 
            commands.append("bg_color black")

    if not commands:
        # Default load and sticks
        commands.extend(["load molecule.sdf", "show sticks", "zoom"])

    return "\n".join(commands)


def query_ollama_for_pymol(prompt: str) -> str:
    """
    Queries local Ollama qwen2.5-coder:7b server to generate raw PyMOL commands.
    
    Falls back to local fallback_pymol_mapper if offline or fails.
    Enforces strict timeout to prevent UI hangs.
    
    Args:
        prompt: User visualization request in natural language
    
    Returns:
        String of PyMOL commands (either from Ollama or fallback mapper)
    """
    model_name = config.OLLAMA_MODEL
    api_endpoint = f"{config.OLLAMA_API_URL.rstrip('/')}/api/chat"
    system_instruction = (
        "You are an expert PyMOL scripting system. Your job is to translate user "
        "visualization requests into raw, executable PyMOL command-line APIs. "
        "Output ONLY raw PyMOL commands, one per line. "
        "Do NOT include markdown block fencing, do NOT include python wrappers, "
        "do NOT include prose, comments, or explanations. "
        "For example, if the user asks to show the molecule as cartoon, output 'show cartoon' and nothing else."
    )

    if not config.OLLAMA_ENABLED:
        logger.info("Ollama integration is disabled by configuration. Using local PyMOL mapper.")
        return fallback_pymol_mapper(prompt)

    try:
        response = requests.post(
            api_endpoint,
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "options": {
                    "temperature": 0.0,
                    "num_predict": 40
                },
                "stream": False
            },
            timeout=OLLAMA_TIMEOUT
        )
        if response.status_code == 200:
            result = response.json()
            pymol_commands = result.get("message", {}).get("content", "").strip()
            if pymol_commands:
                logger.info("Ollama successfully generated PyMOL commands.")
                return pymol_commands
            else:
                raise Exception("Empty response from Ollama")
        else:
            raise Exception(f"HTTP status code {response.status_code}")
    except requests.Timeout:
        logger.warning(f"Ollama request timed out ({OLLAMA_TIMEOUT}s). Using fallback.")
        return fallback_pymol_mapper(prompt)
    except Exception as e:
        logger.warning(f"Ollama qwen2.5-coder:7b unavailable. Triggering fallback. Error: {e}")
        return fallback_pymol_mapper(prompt)


def execute_pymol_commands(commands_text: str) -> bool:
    """
    Pipes raw PyMOL script text directly to stdin of local PyMOL subprocess.
    
    Safely handles cases where PyMOL is offline or commands are invalid.
    
    Args:
        commands_text: Raw PyMOL command text to execute
    
    Returns:
        True if command was successfully sent to PyMOL, False otherwise
    """
    proc = get_pymol_process()
    if proc:
        try:
            logger.info(f"Writing commands to running PyMOL subprocess:\n{commands_text}")
            proc.stdin.write(commands_text + "\n")
            proc.stdin.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to write to PyMOL subprocess stdin: {e}")
            return False
    
    logger.warning("PyMOL subprocess not available")
    return False
