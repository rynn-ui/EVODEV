"""Configuration manager for EvoDev."""

import json
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class EvoDevConfig(BaseModel):
    """Global configuration settings for EvoDev."""

    # Product Branding
    product_name: str = Field(default="EvoDev", description="Configurable name of the tool")

    # Storage Paths
    data_dir: Path = Field(
        default_factory=lambda: Path(os.environ.get("EVODEV_DATA_DIR", Path.home() / ".evodev")),
        description="Root directory for EvoDev data, database, and profiles",
    )
    db_name: str = Field(default="evodev.db", description="Name of the SQLite database file")

    # Profile Settings
    default_profile_name: str = Field(
        default="Default", description="Name of the default experience profile"
    )

    # Privacy & Security
    secret_redaction_enabled: bool = Field(
        default=True, description="Enable automatic masking of credentials and secrets"
    )
    secret_entropy_threshold: float = Field(
        default=4.5, description="Shannon entropy threshold for candidate secret strings"
    )
    ignored_patterns: List[str] = Field(
        default_factory=lambda: [
            ".env*",
            "*.pem",
            "*.key",
            "id_rsa*",
            "*secret*",
            "*.p12",
            "*.keystore",
            "node_modules",
            ".git",
            "__pycache__",
        ],
        description="Glob patterns excluded from diff and content analysis",
    )

    # Experience & Learning Engine
    min_confidence_threshold: float = Field(
        default=0.70, description="Minimum Bayesian confidence required for lesson promotion"
    )
    promotion_min_occurrences: int = Field(
        default=2, description="Minimum independent verified occurrences before promoting to global"
    )
    retention_days: int = Field(
        default=90, description="Retention window in days for raw transcripts/events"
    )
    max_stored_experiences: int = Field(
        default=10000, description="Maximum number of historical experience records retained"
    )

    # Local Service & Dashboard
    server_host: str = Field(default="127.0.0.1", description="Binding host for local API daemon")
    server_port: int = Field(default=8765, description="Port for local API daemon and dashboard")

    # Profile Export/Import Limits
    max_profile_uncompressed_bytes: int = Field(
        default=50 * 1024 * 1024, description="Maximum allowed uncompressed profile size (50MB)"
    )
    max_profile_single_entry_bytes: int = Field(
        default=20 * 1024 * 1024, description="Maximum single file entry size in .vxp (20MB)"
    )

    @property
    def db_path(self) -> Path:
        """Returns the full path to the SQLite database."""
        return self.data_dir / self.db_name

    @property
    def profiles_dir(self) -> Path:
        """Returns the directory where exported and managed profiles reside."""
        return self.data_dir / "profiles"

    @property
    def exports_dir(self) -> Path:
        """Returns the directory where exported .vxp files reside."""
        return self.data_dir / "exports"

    def ensure_directories(self) -> None:
        """Ensure all required runtime directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)


_GLOBAL_CONFIG: Optional[EvoDevConfig] = None


def load_config(custom_path: Optional[Path] = None) -> EvoDevConfig:
    """Load configuration from file or environment."""
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is not None and custom_path is None:
        return _GLOBAL_CONFIG

    # Check local workspace .evodev/config.json, then custom_path, then home
    candidate_paths = []
    if custom_path:
        candidate_paths.append(custom_path)
    candidate_paths.extend([
        Path(".evodev") / "config.json",
        Path.home() / ".evodev" / "config.json",
    ])

    loaded_dict = {}
    for path in candidate_paths:
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded_dict = json.load(f)
                break
            except Exception:
                pass

    # Override with environment variables
    if "EVODEV_PRODUCT_NAME" in os.environ:
        loaded_dict["product_name"] = os.environ["EVODEV_PRODUCT_NAME"]
    if "EVODEV_DATA_DIR" in os.environ:
        loaded_dict["data_dir"] = Path(os.environ["EVODEV_DATA_DIR"])
    if "EVODEV_SERVER_PORT" in os.environ:
        try:
            loaded_dict["server_port"] = int(os.environ["EVODEV_SERVER_PORT"])
        except ValueError:
            pass

    config = EvoDevConfig(**loaded_dict)
    config.ensure_directories()
    _GLOBAL_CONFIG = config
    return config


def set_config(config: EvoDevConfig) -> None:
    """Explicitly set the global configuration instance (useful for tests)."""
    global _GLOBAL_CONFIG
    config.ensure_directories()
    _GLOBAL_CONFIG = config


def save_config(config: EvoDevConfig, target_path: Optional[Path] = None) -> Path:
    """Persist the current configuration to disk."""
    path = target_path or (config.data_dir / "config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2))
    return path
