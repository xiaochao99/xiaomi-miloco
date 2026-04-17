#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# BUILD_TYPE: Release, Debug
BUILD_TYPE="${BUILD_TYPE:-Release}"

# Build support native cpu architecture (ON)/ all cpu architectures (OFF)
NATIVE_ARCS="${NATIVE_ARCS:-OFF}"

AI_ENGINE_DIR="${PROJECT_ROOT}/miloco_ai_engine/core"
BUILD_DIR="${BUILD_DIR:-${PROJECT_ROOT}/build/ai_engine_cpu}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/output}"

if [ "${KEEP_OUTPUT:-0}" != "1" ]; then
    rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${BUILD_DIR}" "${OUTPUT_DIR}"

cmake -S "${AI_ENGINE_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
    -DGGML_CUDA=OFF \
    -DGGML_NATIVE=${NATIVE_ARCS}

cmake --build "${BUILD_DIR}" --target llama-mico -j"$(nproc)"
cmake --install "${BUILD_DIR}" --prefix "${OUTPUT_DIR}"

