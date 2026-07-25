import logging  # noqa: E402
import requests  # noqa: E402
from typing import Optional  # noqa: E402

logger = logging.getLogger("KineticSketch.Visualizer")

from app.config import get_config  # noqa: E402

config = get_config()

OLLAMA_TIMEOUT = 60.0
PYMOL_LISTEN_TIMEOUT = float(config.PYMOL_LISTEN_TIMEOUT)

def get_pymol_process() -> None:
    """Return no process because visualization is handled by 3Dmol.js."""
    if not config.PYMOL_ENABLED:
        logger.info("PyMOL integration is disabled by configuration.")
        return None
    return None


def map_prompt_to_pymol_commands(prompt: str, structure_filename: Optional[str] = None) -> str:
    """
    Double-insurance local translation dictionary.

    Invoked if Ollama server is offline or model is not loaded.
    Translates standard molecular instructions directly to PyMOL APIs.

    Args:
        prompt: User visualization request in natural language
        structure_filename: Optional filename of the target structure

    Returns:
        String of PyMOL commands, one per line
    """
    prompt_l = prompt.lower()
    commands = []

    target_file = structure_filename if structure_filename else "target_structure.sdf"

    # Analyze commands
    if "load" in prompt_l or "open" in prompt_l:
        commands.append(f"load {target_file}")
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
        target = structure_filename if structure_filename else "all"
        commands.extend([f"show sticks {target}", f"zoom {target}"])

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
    # llama.cpp server exposes an OpenAI-compatible API at /v1/chat/completions
    api_endpoint = f"{config.OLLAMA_API_URL.rstrip('/')}/v1/chat/completions"
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
        return map_prompt_to_pymol_commands(prompt)

    try:
        response = requests.post(  # nosec B113
            api_endpoint,
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 40,
                "stream": False
            },
            timeout=float(config.OLLAMA_TIMEOUT)
        )
        if response.status_code == 200:
            result = response.json()
            # OpenAI-compatible format: choices[0].message.content
            pymol_commands = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if pymol_commands:
                logger.info("llama.cpp server successfully generated PyMOL commands.")
                return pymol_commands
            else:
                raise Exception("Empty response from llama.cpp server")
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
    except requests.Timeout:
        logger.warning(f"llama.cpp request timed out ({config.OLLAMA_TIMEOUT}s). Using fallback.")
        return map_prompt_to_pymol_commands(prompt)
    except Exception as e:
        logger.warning(f"llama.cpp server unavailable. Triggering fallback. Error: {e}")
        return map_prompt_to_pymol_commands(prompt)


def execute_pymol_commands(commands_text: str) -> bool:
    """
    Logs the generated PyMOL commands for audit purposes.

    The legacy stdin pipe to a desktop PyMOL process has been removed.
    3D visualization is now handled client-side by 3Dmol.js in the browser.
    Commands generated by the Ollama assistant are returned to the frontend
    via the /api/chat REST endpoint for optional display or future use.

    Args:
        commands_text: Raw PyMOL command text generated by Ollama or fallback mapper

    Returns:
        True always — command logging is always successful
    """
    logger.info(f"PyMOL command generated (browser 3Dmol.js active):\n{commands_text}")
    return True
