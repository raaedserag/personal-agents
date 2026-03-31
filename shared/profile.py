"""
Profile Loader — Reads job profile YAML configs.

Each agent receives its profile_id at startup and uses this module
to load its configuration (integrations, team members, scope, etc.).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROFILES_DIR = Path("/app/profiles")


def load_profile(profile_id: str, profiles_dir: str | Path | None = None) -> dict[str, Any]:
    """Load a job profile by ID.

    Args:
        profile_id: The profile identifier (e.g., "yassir", "zeal")
        profiles_dir: Directory containing profile YAML files

    Returns:
        Parsed profile dict with environment variables resolved.
    """
    base_dir = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    profile_path = base_dir / f"{profile_id}.yaml"

    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path) as f:
        raw = yaml.safe_load(f)

    # Resolve environment variable references (${VAR_NAME})
    return _resolve_env_vars(raw)


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in a config dict."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            var_name = obj[2:-1]
            return os.getenv(var_name, "")
        return obj
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def get_integrations(profile: dict, integration_name: str) -> dict[str, Any]:
    """Extract a specific integration config from a profile.

    Args:
        profile: Loaded profile dict
        integration_name: e.g., "jira", "github", "slack"

    Returns:
        Integration config dict, or empty dict if not configured.
    """
    return profile.get("integrations", {}).get(integration_name, {})


def get_team_members(profile: dict) -> list[dict[str, str]]:
    """Get hardcoded team members from a profile.

    Returns:
        List of dicts with 'name', 'email', 'role' keys.
    """
    return profile.get("team_members", [])


def get_scope(profile: dict) -> str:
    """Get the profile scope: 'leader', 'individual', or 'personal'."""
    return profile.get("scope", "individual")


def list_profiles(profiles_dir: str | Path | None = None) -> list[str]:
    """List all available profile IDs."""
    base_dir = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    if not base_dir.exists():
        return []
    return [p.stem for p in base_dir.glob("*.yaml")]
