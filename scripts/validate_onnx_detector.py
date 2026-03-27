#!/usr/bin/env python3
"""
Quick ONNX validation utility for detection models.

Features:
1) Prints ONNX model input/output metadata
2) Runs one random forward pass with onnxruntime
3) Prints output tensor shapes for parser compatibility check

Usage:
  python scripts/validate_onnx_detector.py --model ./models/yolo26n.onnx
  python scripts/validate_onnx_detector.py --model ./models/yolo26n.onnx --imgsz 640 --provider cpu
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ONNX detection model with onnxruntime.")
    parser.add_argument("--model", type=Path, required=True, help="Path to ONNX model.")
    parser.add_argument("--imgsz", type=int, default=640, help="Input size used for dummy inference.")
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Execution provider selection.",
    )
    parser.add_argument("--batch", type=int, default=1, help="Dummy batch size.")
    return parser.parse_args()


def choose_providers(ort, provider: str) -> list[str]:
    available = ort.get_available_providers()
    if provider == "cuda":
        if "CUDAExecutionProvider" not in available:
            raise RuntimeError(f"CUDA provider unavailable. Available providers: {available}")
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if provider == "cpu":
        return ["CPUExecutionProvider"]
    # auto
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def main() -> int:
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    if not model_path.exists():
        print(f"[ERROR] ONNX file not found: {model_path}")
        return 1

    try:
        import onnxruntime as ort
    except ImportError:
        print("[ERROR] Missing dependency: onnxruntime")
        print("Install it with: pip install onnxruntime")
        return 1

    providers = choose_providers(ort, args.provider)
    print(f"[INFO] Model: {model_path}")
    print(f"[INFO] Providers: {providers}")

    try:
        sess = ort.InferenceSession(str(model_path), providers=providers)
    except Exception as exc:
        print(f"[ERROR] Failed to create ONNX session: {exc}")
        return 2

    inputs = sess.get_inputs()
    outputs = sess.get_outputs()
    if not inputs:
        print("[ERROR] Model has no inputs.")
        return 3

    print("[INFO] Inputs:")
    for i, inp in enumerate(inputs):
        print(f"  - [{i}] name={inp.name}, shape={inp.shape}, type={inp.type}")

    print("[INFO] Outputs:")
    for i, out in enumerate(outputs):
        print(f"  - [{i}] name={out.name}, shape={out.shape}, type={out.type}")

    # Build dummy input from first input tensor spec.
    input_tensor = np.random.rand(args.batch, 3, args.imgsz, args.imgsz).astype(np.float32)
    input_name = inputs[0].name

    try:
        result = sess.run(None, {input_name: input_tensor})
    except Exception as exc:
        print(f"[ERROR] Inference failed: {exc}")
        return 4

    print("[OK] Inference success.")
    for i, arr in enumerate(result):
        shape = getattr(arr, "shape", None)
        dtype = getattr(arr, "dtype", None)
        print(f"  - output[{i}] shape={shape}, dtype={dtype}")

    # Quick heuristic for current parser in miloco_server/detection/detector.py
    # Existing parser expects single output with shape close to [1, 84, N] or [1, N, 84].
    if len(result) == 1 and hasattr(result[0], "shape") and len(result[0].shape) == 3:
        _, d1, d2 = result[0].shape
        if 84 in (d1, d2):
            print("[HINT] Output looks compatible with current YOLOv8-style parser.")
        else:
            print("[HINT] Output shape may require parser adaptation in detector.py.")
    else:
        print("[HINT] Multi-output or non-3D output detected; parser adaptation is likely required.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
