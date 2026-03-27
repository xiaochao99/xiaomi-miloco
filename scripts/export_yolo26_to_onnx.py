#!/usr/bin/env python3
"""
Export YOLO26 PyTorch checkpoint (.pt) to ONNX.

Usage examples:
  python scripts/export_yolo26_to_onnx.py --weights yolo26n.pt
  python scripts/export_yolo26_to_onnx.py --weights yolo26n.pt --imgsz 640 --opset 13 --dynamic
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export YOLO26 .pt model to ONNX format.",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("yolo26n.pt"),
        help="Path to YOLO26 .pt checkpoint.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output ONNX path. Default: same directory/name as weights.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size for export.",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=13,
        help="ONNX opset version.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Export device, e.g. cpu / cuda:0",
    )
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="Enable dynamic input shape axes in ONNX.",
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        help="Simplify ONNX graph after export (requires onnxsim).",
    )
    parser.add_argument(
        "--half",
        action="store_true",
        help="Export FP16 model (usually requires CUDA device).",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=1,
        help="Static batch size for export when --dynamic is not used.",
    )
    parser.add_argument(
        "--nms",
        action="store_true",
        help="Export with NMS node (if backend supports).",
    )
    return parser.parse_args()


def _ensure_dependency() -> None:
    if shutil.which("python") is None:
        raise RuntimeError("Python executable not found in PATH.")

    try:
        import ultralytics  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: ultralytics.\n"
            "Install it with: pip install ultralytics onnx"
        ) from exc


def main() -> int:
    args = parse_args()
    _ensure_dependency()

    from ultralytics import YOLO

    weights_path = args.weights.expanduser().resolve()
    if not weights_path.exists():
        print(f"[ERROR] Weights file not found: {weights_path}")
        return 1

    output_path = args.output.expanduser().resolve() if args.output else None
    project_dir = output_path.parent if output_path else weights_path.parent
    output_stem = output_path.stem if output_path else weights_path.stem

    print(f"[INFO] Loading model: {weights_path}")
    model = YOLO(str(weights_path))

    export_kwargs = {
        "format": "onnx",
        "imgsz": args.imgsz,
        "opset": args.opset,
        "device": args.device,
        "dynamic": args.dynamic,
        "simplify": args.simplify,
        "half": args.half,
        "batch": args.batch,
        "nms": args.nms,
        "project": str(project_dir),
        "name": output_stem,
        "exist_ok": True,
    }

    print("[INFO] Exporting to ONNX...")
    exported = model.export(**export_kwargs)
    exported_path = Path(str(exported)).resolve()

    if not exported_path.exists():
        print(f"[ERROR] Export finished but ONNX not found: {exported_path}")
        return 2

    # If user passed --output and ultralytics output name/path differs, move file.
    if output_path and exported_path != output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        exported_path.replace(output_path)
        exported_path = output_path

    print(f"[OK] ONNX exported: {exported_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
