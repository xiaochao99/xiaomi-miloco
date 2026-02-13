# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Model loader for built-in YOLOv8-nano model.
Handles loading model from package resources in various runtime environments.
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, BinaryIO, Union
import sys

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Handles loading of built-in YOLOv8 model files.
    Supports loading from:
    1. Package resources (when installed as package)
    2. Source directory (development mode)
    3. PyInstaller bundle (frozen executable)
    4. Docker container
    """

    MODEL_FILENAME = "yolov8n.onnx"
    MODEL_SIZE = 6340543  # Expected file size in bytes (approx 6MB)

    def __init__(self):
        self._cached_model_path: Optional[str] = None
        self._temp_dir: Optional[str] = None

    def get_model_path(self) -> Optional[str]:
        """
        Get the path to the built-in model file.
        Tries multiple methods to find the model in different environments.
        Priority: /models (Docker shared) > builtin package > source
        
        Returns:
            Path to the model file, or None if not found
        """
        # Return cached path if available
        if self._cached_model_path and os.path.exists(self._cached_model_path):
            return self._cached_model_path

        # Try different loading strategies (in priority order)
        strategies = [
            self._load_from_docker_models,   # /models - shared with ai_engine
            self._load_from_source,           # builtin package
            self._load_from_package,
            self._load_from_pyinstaller,
            self._load_from_site_packages,
        ]

        for strategy in strategies:
            try:
                path = strategy()
                if path and os.path.exists(path):
                    # Verify file size to ensure it's valid
                    if self._verify_model_file(path):
                        self._cached_model_path = path
                        logger.info(f"Model loaded successfully from: {path}")
                        return path
                    else:
                        logger.warning(f"Model file verification failed for: {path}")
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                continue

        logger.error("Could not find built-in model file in any location")
        return None

    def _load_from_docker_models(self) -> Optional[str]:
        """Load model from /models directory (shared with ai_engine in Docker)."""
        # Primary location: /models (mounted from ./models in docker-compose)
        docker_models_path = Path("/models") / self.MODEL_FILENAME
        
        if docker_models_path.exists():
            logger.debug(f"Found model in Docker shared models directory: {docker_models_path}")
            return str(docker_models_path)
        
        # Also check environment variable for custom path
        env_model_path = os.environ.get("YOLO_MODEL_PATH")
        if env_model_path and os.path.exists(env_model_path):
            logger.debug(f"Found model from environment variable: {env_model_path}")
            return env_model_path
            
        return None

    def _load_from_source(self) -> Optional[str]:
        """Load model from source directory (development mode)."""
        # Get the directory containing this file
        current_dir = Path(__file__).parent
        model_path = current_dir / "models" / self.MODEL_FILENAME
        
        if model_path.exists():
            return str(model_path)
        return None

    def _load_from_package(self) -> Optional[str]:
        """Load model from installed package using importlib.resources."""
        try:
            # Python 3.9+ importlib.resources
            from importlib.resources import files
            
            # Get the package reference
            package = "miloco_server.detection"
            
            # Try to get model from package resources
            try:
                model_ref = files(package) / "models" / self.MODEL_FILENAME
                if model_ref.is_file():
                    # For Python 3.9+, we can use as_file context manager
                    # But we need a persistent path, so extract to temp
                    return self._extract_to_temp(model_ref)
            except Exception as e:
                logger.debug(f"importlib.resources.files failed: {e}")
                
        except ImportError:
            # Fallback for older Python versions
            try:
                import pkgutil
                data = pkgutil.get_data("miloco_server.detection", f"models/{self.MODEL_FILENAME}")
                if data:
                    return self._save_bytes_to_temp(data)
            except Exception as e:
                logger.debug(f"pkgutil fallback failed: {e}")
                
        return None

    def _load_from_pyinstaller(self) -> Optional[str]:
        """Load model from PyInstaller bundle."""
        # Check if running in PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running in a PyInstaller bundle
            bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
            
            # Try multiple possible locations
            possible_paths = [
                bundle_dir / "miloco_server" / "detection" / "models" / self.MODEL_FILENAME,
                bundle_dir / "detection" / "models" / self.MODEL_FILENAME,
                bundle_dir / "models" / self.MODEL_FILENAME,
                bundle_dir / self.MODEL_FILENAME,
            ]
            
            for path in possible_paths:
                if path.exists():
                    return str(path)
                    
        return None

    def _load_from_site_packages(self) -> Optional[str]:
        """Load model from site-packages installation."""
        try:
            import miloco_server
            package_dir = Path(miloco_server.__file__).parent
            model_path = package_dir / "detection" / "models" / self.MODEL_FILENAME
            
            if model_path.exists():
                return str(model_path)
        except Exception as e:
            logger.debug(f"site-packages loading failed: {e}")
            
        return None

    def _extract_to_temp(self, model_ref) -> Optional[str]:
        """Extract model from package resource to temporary file."""
        try:
            # Create temp directory if needed
            if not self._temp_dir:
                self._temp_dir = tempfile.mkdtemp(prefix="miloco_model_")
            
            temp_path = os.path.join(self._temp_dir, self.MODEL_FILENAME)
            
            # Only extract if not already exists
            if not os.path.exists(temp_path):
                from importlib.resources import as_file
                
                with as_file(model_ref) as model_path:
                    shutil.copy2(model_path, temp_path)
                logger.debug(f"Extracted model to temp location: {temp_path}")
            
            return temp_path
        except Exception as e:
            logger.error(f"Failed to extract model to temp: {e}")
            return None

    def _save_bytes_to_temp(self, data: bytes) -> Optional[str]:
        """Save model bytes to temporary file."""
        try:
            if not self._temp_dir:
                self._temp_dir = tempfile.mkdtemp(prefix="miloco_model_")
            
            temp_path = os.path.join(self._temp_dir, self.MODEL_FILENAME)
            
            if not os.path.exists(temp_path):
                with open(temp_path, 'wb') as f:
                    f.write(data)
                logger.debug(f"Saved model bytes to temp location: {temp_path}")
            
            return temp_path
        except Exception as e:
            logger.error(f"Failed to save model bytes to temp: {e}")
            return None

    def _verify_model_file(self, path: str) -> bool:
        """Verify that the model file is valid."""
        try:
            file_size = os.path.getsize(path)
            
            # Check minimum size (should be at least 1MB)
            if file_size < 1_000_000:
                logger.warning(f"Model file too small: {file_size} bytes")
                return False
            
            # Check maximum size (should be less than 100MB)
            if file_size > 100_000_000:
                logger.warning(f"Model file too large: {file_size} bytes")
                return False
            
            # Try to read first few bytes to verify it's a valid file
            with open(path, 'rb') as f:
                header = f.read(8)
                if len(header) < 8:
                    logger.warning("Model file too small to be valid")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Model file verification error: {e}")
            return False

    def cleanup(self):
        """Clean up temporary files."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
                logger.debug(f"Cleaned up temp directory: {self._temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {e}")
            finally:
                self._temp_dir = None
                self._cached_model_path = None

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()


# Global loader instance
_model_loader: Optional[ModelLoader] = None


def get_model_loader() -> ModelLoader:
    """Get the global model loader instance."""
    global _model_loader
    if _model_loader is None:
        _model_loader = ModelLoader()
    return _model_loader


def get_builtin_model_path() -> Optional[str]:
    """Convenience function to get built-in model path."""
    return get_model_loader().get_model_path()


def verify_model_exists() -> bool:
    """Verify that the built-in model file exists and is valid."""
    path = get_builtin_model_path()
    return path is not None and os.path.exists(path)
