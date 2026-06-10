from pathlib import Path
from typing import Any

import yaml


def load_ontology_profile(ontology_file: str, profile_name: str) -> dict[str, Any]:
    ontology_path = Path(ontology_file)
    if not ontology_path.is_absolute():
        ontology_path = Path.cwd() / ontology_path

    with ontology_path.open("r", encoding="utf-8") as handle:
        ontology = yaml.safe_load(handle) or {}

    profiles = ontology.get("profiles", {})
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles)) or "<none>"
        raise ValueError(
            f"Ontology profile '{profile_name}' was not found in {ontology_path}. "
            f"Available profiles: {available}"
        )

    return profiles[profile_name]


def resolve_local_path(path_value: str, base_file: str | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path

    if base_file:
        base_path = Path(base_file)
        if not base_path.is_absolute():
            base_path = Path.cwd() / base_path
        return base_path.parent / path

    return Path.cwd() / path

