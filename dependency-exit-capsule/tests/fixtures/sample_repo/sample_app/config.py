import toml
from pathlib import Path

def parse_config(filepath: str) -> dict:
    """Read a toml file using legacy toml package."""
    return toml.load(filepath)
