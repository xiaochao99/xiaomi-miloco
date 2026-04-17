# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
LLaMA-MICO Library Manager
Manages library loading, releasing and memory management
"""

import ctypes
import ctypes.util
import os
import threading
import logging
from typing import Optional
from miloco_ai_engine.middleware.exceptions import CoreNormalException, InvalidArgException
logger = logging.getLogger(__name__)

LLAMA_MICO_LIB_NAME = "llama-mico"  # Library name

class LibraryManager:
    """Library manager - Singleton pattern"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):  # Singleton pattern, avoid duplicate initialization
            return

        self._initialized = True
        self._library = None
        self._function_loaded = False

    def _get_library_path(self):
        """Get library path"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = []

        # Allow overriding via env (useful in containers)
        env_lib_dir = os.environ.get("LLAMA_MICO_LIB_DIR") or os.environ.get("MICO_LIB_DIR")
        if env_lib_dir:
            candidates.append(env_lib_dir)

        # Default repo-relative path
        candidates.append(os.path.join(current_dir, "..", "..", "output", "lib"))

        # Common container output path used by runtime images
        candidates.append(os.path.join(os.sep, "app", "output", "lib"))

        for lib_dir in candidates:
            lib_dir = os.path.abspath(lib_dir)
            if os.path.isdir(lib_dir):
                return lib_dir

        logger.error("Library directory not found. Tried: %s", candidates)
        raise InvalidArgException(f"Library directory not found. Tried: {candidates}")

    def _cuda_seems_available(self) -> bool:
        """
        Best-effort CUDA presence check.
        This does not guarantee a usable GPU, but helps decide which library variant to try first.
        """
        # Common device files when running with NVIDIA container runtime
        if os.path.exists(os.path.join(os.sep, "dev", "nvidiactl")):
            return True
        if os.path.exists(os.path.join(os.sep, "proc", "driver", "nvidia", "version")):
            return True
        # Library discovery (works when libcuda is visible in loader paths)
        try:
            return bool(ctypes.util.find_library("cuda"))
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def _load_error_looks_like_missing_cuda(self, err: BaseException) -> bool:
        msg = str(err)
        needles = [
            "libcuda.so.1",
            "libcudart.so",
            "libnvidia-ml.so",
            "cannot open shared object file",
        ]
        return any(n in msg for n in needles) and ("cuda" in msg or "nvidia" in msg)

    def _candidate_library_names(self) -> list[str]:
        """
        Build candidate library filenames to try.
        Supports GPU/CPU variants via env vars.
        """
        mode = (os.environ.get("LLAMA_MICO_LIB_MODE") or "auto").strip().lower()
        # Optional explicit filenames (relative to lib_dir)
        gpu_name = (os.environ.get("LLAMA_MICO_GPU_LIB_NAME") or "").strip()
        cpu_name = (os.environ.get("LLAMA_MICO_CPU_LIB_NAME") or "").strip()

        base_gpu = f"lib{LLAMA_MICO_LIB_NAME}.so"
        # Common CPU variant names used in builds
        cpu_variants = [
            f"lib{LLAMA_MICO_LIB_NAME}-cpu.so",
            f"lib{LLAMA_MICO_LIB_NAME}_cpu.so",
            f"lib{LLAMA_MICO_LIB_NAME}.cpu.so",
        ]

        gpu_candidates = [gpu_name] if gpu_name else [base_gpu]
        cpu_candidates = ([cpu_name] if cpu_name else []) + cpu_variants

        # Decide priority
        if mode == "gpu":
            return gpu_candidates + cpu_candidates
        if mode == "cpu":
            return cpu_candidates + gpu_candidates

        # auto
        if self._cuda_seems_available():
            return gpu_candidates + cpu_candidates
        return cpu_candidates + gpu_candidates

    def _candidate_library_dirs(self) -> list[str]:
        """
        Candidate directories (ordered) for loading libraries.
        Supports packaging CPU/GPU libs into separate directories:
        - /app/output/lib/gpu
        - /app/output/lib/cpu
        """
        mode = (os.environ.get("LLAMA_MICO_LIB_MODE") or "auto").strip().lower()

        # Explicit override always wins.
        env_lib_dir = os.environ.get("LLAMA_MICO_LIB_DIR") or os.environ.get("MICO_LIB_DIR")
        candidates: list[str] = []
        if env_lib_dir:
            candidates.append(env_lib_dir)

        # Common packaged dirs
        gpu_dir = os.path.join(os.sep, "app", "output", "lib", "gpu")
        cpu_dir = os.path.join(os.sep, "app", "output", "lib", "cpu")
        base_dir = os.path.join(os.sep, "app", "output", "lib")

        if mode == "gpu":
            candidates += [gpu_dir, base_dir, cpu_dir]
        elif mode == "cpu":
            candidates += [cpu_dir, base_dir, gpu_dir]
        else:
            # auto: prefer GPU when CUDA seems available
            if self._cuda_seems_available():
                candidates += [gpu_dir, base_dir, cpu_dir]
            else:
                candidates += [cpu_dir, base_dir, gpu_dir]

        # Repo-relative path (dev)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(current_dir, "..", "..", "output", "lib"))

        # Dedup while preserving order
        out: list[str] = []
        for d in candidates:
            d = os.path.abspath(d)
            if d not in out:
                out.append(d)
        return out

    def _load_library(self) -> Optional[ctypes.CDLL]:
        """Load library"""
        if self._library is not None:
            return self._library

        last_load_error: Optional[BaseException] = None
        found_any_candidate = False

        # Get library search dirs
        lib_dirs = [d for d in self._candidate_library_dirs() if os.path.isdir(d)]
        if not lib_dirs:
            # fallback to old behavior (for backward compatibility)
            lib_dirs = [self._get_library_path()]
        # Library name list (prefer Linux .so in containers)
        library_names = self._candidate_library_names() + [
            f"lib{LLAMA_MICO_LIB_NAME}.dylib",  # macOS
            f"{LLAMA_MICO_LIB_NAME}.dll",  # Windows
            LLAMA_MICO_LIB_NAME,  # Generic name
        ]

        # Try to load library from specific directories first
        for lib_dir in lib_dirs:
            for lib_name in library_names:
                lib_path = os.path.join(lib_dir, lib_name)
                if not os.path.exists(lib_path):
                    logger.warning("Library file not found: %s", lib_path)
                    continue
                found_any_candidate = True
                logger.info("Attempting to load library from: %s", lib_path)
                try:
                    # Ensure dependent .so resolve from the same directory first.
                    prev_ld = os.environ.get("LD_LIBRARY_PATH", "")
                    if lib_dir and (not prev_ld.startswith(lib_dir)):
                        os.environ["LD_LIBRARY_PATH"] = f"{lib_dir}:{prev_ld}" if prev_ld else lib_dir

                    # Load library using RTLD_GLOBAL mode with full path
                    self._library = ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
                    logger.info("LLaMA-MICO library loaded successfully from: %s", lib_path)
                    return self._library
                except Exception as e: # pylint: disable=broad-exception-caught
                    last_load_error = e
                    logger.warning("Cannot load library from %s: %s", lib_path, e)
                    # If GPU library is present but CUDA deps are missing, try CPU variants next.
                    if self._load_error_looks_like_missing_cuda(e):
                        logger.warning("Library load failed due to missing CUDA deps; will try CPU variants if available")
                    continue

        # Try to load from system path
        # NOTE: ctypes.util.find_library expects a "library name", not a filename.
        # Passing "libxxx.so" often returns None; ctypes.CDLL(None) then loads the
        # main program (e.g. python3), which later causes confusing errors like:
        # "python3: undefined symbol: llama_mico_init".
        system_names = [LLAMA_MICO_LIB_NAME, f"lib{LLAMA_MICO_LIB_NAME}"]
        for name in system_names:
            logger.info("Attempting to locate library from system path: %s", name)
            try:
                found = ctypes.util.find_library(name)
                if not found:
                    logger.warning("ctypes.util.find_library(%s) returned None", name)
                    continue
                logger.info("Attempting to load library from system path: %s", found)
                self._library = ctypes.CDLL(found, mode=ctypes.RTLD_GLOBAL)
                logger.info("LLaMA-MICO library loaded from system path: %s", found)
                return self._library
            except Exception as e: # pylint: disable=broad-exception-caught
                last_load_error = e
                logger.warning("Cannot load library from system path %s: %s", name, e)
                continue

        if found_any_candidate and last_load_error is not None:
            # We did find the library file(s), but dynamic loading failed due to missing deps
            # (e.g. "libcuda.so.1: cannot open shared object file").
            logger.error("Found LLaMA-MICO library but failed to load it: %s", last_load_error)
            raise InvalidArgException(f"Found LLaMA-MICO library but failed to load it: {last_load_error}") from last_load_error

        logger.error("Cannot find LLaMA-MICO dynamic library")
        raise InvalidArgException("Cannot find LLaMA-MICO dynamic library")

    def _setup_function_signatures(self):
        """Setup function signatures"""
        if self._library is None:
            logger.error("Library not loaded")
            raise InvalidArgException("Library not loaded")

        try:
            # Initialize function
            self._library.llama_mico_init.restype = ctypes.c_int32
            self._library.llama_mico_init.argtypes = [
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_void_p)
            ]

            # Free function
            self._library.llama_mico_free.restype = ctypes.c_int32
            self._library.llama_mico_free.argtypes = [ctypes.c_void_p]

            # Prompt request function
            self._library.llama_mico_request_prompt.restype = ctypes.c_int32
            self._library.llama_mico_request_prompt.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # request_json_str
                ctypes.POINTER(ctypes.c_int32),  # is_finished
                ctypes.POINTER(ctypes.c_char_p)  # content
            ]

            # Generate request function
            self._library.llama_mico_request_generate.restype = ctypes.c_int32
            self._library.llama_mico_request_generate.argtypes = [
                ctypes.c_void_p,  # handle
                ctypes.c_char_p,  # request_json_str
                ctypes.POINTER(ctypes.c_int32),  # is_finished
                ctypes.POINTER(ctypes.c_char_p)  # content
            ]

            logger.info("Function signatures setup successfully")
            self._function_loaded = True
            return True

        except Exception as e:
            logger.error("Failed to setup function signatures: %s", e)
            raise CoreNormalException(f"Failed to setup function signatures: {e}") from e

    def get_library(self) -> Optional[ctypes.CDLL]:
        """Get library instance"""
        if self._library is None:
            self._load_library()
        if self._library and not self._function_loaded:
            self._setup_function_signatures()
        return self._library

# Global library manager instance
lib_manager = LibraryManager()


def get_library() -> Optional[ctypes.CDLL]:
    """Convenience function to get library instance"""
    lib = lib_manager.get_library()
    if not lib:
        logger.error("LLaMA-MICO library not loaded")
        raise CoreNormalException("LLaMA-MICO library not loaded")
    return lib
