#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# BUILD_TYPE: Release, Debug
BUILD_TYPE=Release

# Build CUDA architectures. Please modify it according to your own needs if necessary. 
# For reference https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/#gpu-feature-list
# Note: Use spaces to separate architectures, not semicolons
CUDA_ARCS="61 75 80 86 89 90 120" # added 61 for Pascal GPUs (Tesla P40, GTX 10xx series), 120 for Blackwell (RTX 5060 Ti)

# Build support native cpu architecture (ON)/ all cpu architectures (OFF)
NATIVE_ARCS=OFF

AI_ENGINE_DIR="${PROJECT_ROOT}/miloco_ai_engine/core"
BUILD_DIR="${BUILD_DIR:-${PROJECT_ROOT}/build/ai_engine_cuda}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/output}"

if [ "${KEEP_OUTPUT:-0}" != "1" ]; then
    rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${BUILD_DIR}" "${OUTPUT_DIR}"

cmake -S "${AI_ENGINE_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
    -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCS} \
    -DGGML_CUDA=ON \
    -DGGML_NATIVE=${NATIVE_ARCS} \
    -DCMAKE_CXX_FLAGS="-fno-gcse -fno-fat-lto-objects"

cmake --build "${BUILD_DIR}" --target llama-mico -j"$(nproc)"
cmake --install "${BUILD_DIR}" --prefix "${OUTPUT_DIR}"