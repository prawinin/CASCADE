"""
KineticSketch AI - Centralized Configuration Management

This module loads environment variables and provides defaults for:
- Flask/Taipy server settings
- PyMOL integration parameters
- Ollama AI integration
- Molecular processing limits
- Logging configuration
"""

import os  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402
from typing import Optional, Dict, Any  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from app.paths import CACHE_DIR, PROJECT_ROOT
from app.runtime import select_available_port

# Load environment variables from .env file at the root of the project
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Config:
    """Base configuration class with environment-aware settings."""

    # Environment
    ENVIRONMENT = os.getenv("FLASK_ENV", "development")
    DEBUG = ENVIRONMENT != "production"
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.getenv("SECRET_KEY", "dev-key-change-in-production"))

    # Server
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = select_available_port(HOST, requested=os.getenv("PORT"), preferred=7860)

    # PyMOL Integration
    PYMOL_SERVER_HOST = os.getenv("PYMOL_SERVER_HOST", "localhost")
    PYMOL_SERVER_PORT = int(os.getenv("PYMOL_SERVER_PORT", 9123))
    PYMOL_LISTEN_TIMEOUT = int(os.getenv("PYMOL_LISTEN_TIMEOUT", 5))
    PYMOL_ENABLED = os.getenv("PYMOL_ENABLED", "1").lower() in ("1", "true", "yes")
    GNINA_ENABLED = os.getenv("GNINA_ENABLED", "1").lower() in ("1", "true", "yes")

    # Ollama AI Integration
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 15))
    OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1").lower() in ("1", "true", "yes")

    # Molecular Processing
    MOLECULE_SIZE_LIMIT = int(os.getenv("MOLECULE_SIZE_LIMIT", 200))
    SMILES_LENGTH_LIMIT = int(os.getenv("SMILES_LENGTH_LIMIT", 2000))

    # Async Queue (Celery/Redis)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MODEL_DEVICE = os.getenv("MODEL_DEVICE", "cpu").lower()

    # Caching
    PDB_CACHE_TTL = int(os.getenv("PDB_CACHE_TTL", 3600))  # 1 hour in seconds
    PDB_CACHE_DIR = os.getenv("PDB_CACHE_DIR", str(CACHE_DIR / "pdb_cache"))

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "text"
    LOG_FILE = os.getenv("LOG_FILE", str(CACHE_DIR / "kinetic_sketch.log"))

    # Development
    ENABLE_DEBUG_CONSOLE = os.getenv("ENABLE_DEBUG_CONSOLE", "0").lower() in ("1", "true", "yes")
    ENABLE_CORS = os.getenv("ENABLE_CORS", "0").lower() in ("1", "true", "yes")
    EMBEDDED_MODE = os.getenv("EMBEDDED_MODE", "0").lower() in ("1", "true", "yes")
    _FRAME_ANCESTORS_RAW = os.getenv("FRAME_ANCESTORS", "'none'").strip() or "'none'"
    FRAME_ANCESTORS = (
        "'none'" if _FRAME_ANCESTORS_RAW.lower() in {"none", "'none'"}
        else _FRAME_ANCESTORS_RAW
    )
    REQUIRE_REDIS = os.getenv("REQUIRE_REDIS", "1").lower() in ("1", "true", "yes")
    REQUIRE_MODEL = os.getenv("REQUIRE_MODEL", "1").lower() in ("1", "true", "yes")
    REQUIRE_DRUG_DATA = os.getenv("REQUIRE_DRUG_DATA", "0").lower() in ("1", "true", "yes")
    TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "0"))
    ACTION_LOGGING_ENABLED = os.getenv("ACTION_LOGGING_ENABLED", "0").lower() in ("1", "true", "yes")
    REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "1").lower() in ("1", "true", "yes")

    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """
        Validate critical configuration values.

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []

        if cls.MOLECULE_SIZE_LIMIT < 1 or cls.MOLECULE_SIZE_LIMIT > 1000:
            errors.append(f"MOLECULE_SIZE_LIMIT must be 1-1000, got {cls.MOLECULE_SIZE_LIMIT}")

        if cls.SMILES_LENGTH_LIMIT < 10 or cls.SMILES_LENGTH_LIMIT > 10000:
            errors.append(f"SMILES_LENGTH_LIMIT must be 10-10000, got {cls.SMILES_LENGTH_LIMIT}")

        if cls.PORT < 1 or cls.PORT > 65535:
            errors.append(f"PORT must be 1-65535, got {cls.PORT}")

        if cls.PYMOL_LISTEN_TIMEOUT < 1 or cls.PYMOL_LISTEN_TIMEOUT > 60:
            errors.append(f"PYMOL_LISTEN_TIMEOUT must be 1-60s, got {cls.PYMOL_LISTEN_TIMEOUT}")

        if cls.OLLAMA_TIMEOUT < 1 or cls.OLLAMA_TIMEOUT > 300:
            errors.append(f"OLLAMA_TIMEOUT must be 1-300s, got {cls.OLLAMA_TIMEOUT}")

        if cls.MODEL_DEVICE not in ("cpu", "cuda", "auto"):
            errors.append("MODEL_DEVICE must be one of: cpu, cuda, auto")

        if cls.TRUST_PROXY_HOPS < 0 or cls.TRUST_PROXY_HOPS > 10:
            errors.append("TRUST_PROXY_HOPS must be between 0 and 10")

        frame_ancestors = cls.FRAME_ANCESTORS.split()
        if not frame_ancestors:
            errors.append("FRAME_ANCESTORS must not be empty")
        elif "'none'" in frame_ancestors and frame_ancestors != ["'none'"]:
            errors.append("FRAME_ANCESTORS 'none' cannot be combined with other sources")
        else:
            for source in frame_ancestors:
                if source in {"'none'", "'self'"}:
                    continue
                parsed = urlsplit(source)
                try:
                    parsed_port = parsed.port
                except ValueError:
                    parsed_port = -1
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed_port is not None
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                ):
                    errors.append(
                        "FRAME_ANCESTORS entries must be 'none', 'self', or exact "
                        f"HTTPS origins without paths; got {source!r}"
                    )

        return len(errors) == 0, errors

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """
        Export all configuration as dictionary (sanitize sensitive values).

        Returns:
            Dictionary of configuration values with sensitive data masked
        """
        config_dict = {}
        for key in dir(cls):
            if key.isupper() and not key.startswith("_"):
                value = getattr(cls, key)
                # Mask sensitive values
                if key in ("SECRET_KEY",):
                    value = "***REDACTED***"
                config_dict[key] = value
        return config_dict

    @classmethod
    def log_startup_info(cls) -> str:
        """
        Generate startup information banner.

        Returns:
            Formatted startup info string
        """
        lines = [
            f"{'='*60}",
            "KineticSketch AI - Startup Configuration",
            f"{'='*60}",
            f"Environment:        {cls.ENVIRONMENT}",
            f"Debug Mode:         {cls.DEBUG}",
            f"Server:             {cls.HOST}:{cls.PORT}",
            f"PyMOL Integration:  {' Enabled' if cls.PYMOL_ENABLED else ' Disabled'}",
            f"Ollama Integration: {' Enabled' if cls.OLLAMA_ENABLED else ' Disabled'}",
            f"Molecule Limit:     {cls.MOLECULE_SIZE_LIMIT} atoms",
            f"SMILES Length Limit: {cls.SMILES_LENGTH_LIMIT} chars",
            f"Logging Level:      {cls.LOG_LEVEL}",
            f"Log Format:         {cls.LOG_FORMAT}",
            f"{'='*60}",
        ]
        return "\n".join(lines)


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    ENVIRONMENT = "development"
    ENABLE_DEBUG_CONSOLE = True
    ENABLE_CORS = True


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    ENVIRONMENT = "production"
    ENABLE_DEBUG_CONSOLE = False
    ENABLE_CORS = False


class TestingConfig(Config):
    """Testing environment configuration."""

    DEBUG = True
    ENVIRONMENT = "testing"
    MOLECULE_SIZE_LIMIT = 50  # Smaller limit for tests
    OLLAMA_TIMEOUT = 5  # Shorter timeout for tests


def get_config(env: Optional[str] = None) -> Config:
    """
    Get configuration class for the specified environment.

    Args:
        env: Environment name ('development', 'production', 'testing').
             If None, uses FLASK_ENV environment variable.

    Returns:
        Configuration class instance

    Raises:
        ValueError: If environment is not recognized
    """
    env = env or os.getenv("FLASK_ENV", "development")

    config_map = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }

    if env not in config_map:
        raise ValueError(
            f"Unknown environment '{env}'. Must be one of: "
            f"{', '.join(config_map.keys())}"
        )

    return config_map[env]


if __name__ == "__main__":
    # Print current configuration on script execution
    config = get_config()
    print(config.log_startup_info())
    print("\nAll Settings:")
    for key, value in sorted(config.to_dict().items()):
        print(f"  {key}: {value}")

    # Validate configuration
    is_valid, errors = config.validate()
    if not is_valid:
        print("\n  Configuration Warnings:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n Configuration is valid")
