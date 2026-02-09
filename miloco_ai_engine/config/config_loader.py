# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Configuration loader module
Common YAML configuration loading functionality
"""

from pathlib import Path
import yaml
from typing import Dict, Any


def load_yaml_config(config_file_path: Path) -> Dict[str, Any]:
    """
    Load configuration from YAML file
    
    Args:
        config_file_path: Path to the YAML configuration file
        
    Returns:
        Dictionary containing the configuration data
        
    Raises:
        FileNotFoundError: If the configuration file is not found
        ValueError: If the YAML file format is invalid
    """
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'Configuration file not found: {config_file_path}') from exc
    except yaml.YAMLError as exc:
        raise ValueError(f'YAML configuration file format error: {exc}') from exc


def get_project_root() -> Path:
    """
    Get the project root directory
    
    Returns:
        Path object pointing to the project root
    """
    return Path(__file__).parent.parent
