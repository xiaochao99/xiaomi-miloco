# syntax=docker/dockerfile:1.4
ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=12.5.1
# Target the CUDA build image.
ARG BASE_CUDA_DEV_CONTAINER=nvidia/cuda:${CUDA_VERSION}-devel-ubuntu${UBUNTU_VERSION}
# Target the CUDA run image.
ARG BASE_CUDA_RUN_CONTAINER=nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu${UBUNTU_VERSION}
# Set apt repository.

ARG APT_MIRRORS_URL=http://archive.ubuntu.com/ubuntu/
ARG APT_FALLBACK_MIRRORS="http://mirrors.aliyun.com/ubuntu/ https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ https://mirrors.ustc.edu.cn/ubuntu/ http://archive.ubuntu.com/ubuntu/"
# Set pip index URL.

ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG DEBIAN_FRONTEND=noninteractive

################################################
# AI Engine Builder
################################################
FROM ${BASE_CUDA_DEV_CONTAINER} AS ai_engine-builder

# Restate apt mirrors repository.
ARG APT_MIRRORS_URL
ARG APT_FALLBACK_MIRRORS

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    set -eux \
    && if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then sed -Ei 's/^Components: .*/Components: main universe restricted multiverse/' /etc/apt/sources.list.d/ubuntu.sources; fi \
    && cp /etc/apt/sources.list.d/ubuntu.sources /tmp/ubuntu.sources.template \
    && mirrors="${APT_MIRRORS_URL%/}/ ${APT_FALLBACK_MIRRORS}" \
    && printf '%s\n' \
        'Acquire::Retries "6";' \
        'Acquire::http::Timeout "30";' \
        'Acquire::https::Timeout "30";' \
        'Acquire::ForceIPv4 "true";' \
        > /etc/apt/apt.conf.d/99-miloco-retries \
    && update_ok=0 \
    && for m in $mirrors; do \
        cp /tmp/ubuntu.sources.template /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i "s|http://archive.ubuntu.com/ubuntu/|${m}|g" /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i "s|http://security.ubuntu.com/ubuntu/|${m}|g" /etc/apt/sources.list.d/ubuntu.sources; \
        if apt-get update; then \
            if apt-cache policy build-essential 2>/dev/null | grep -q 'Candidate: '; then \
                if ! apt-cache policy build-essential 2>/dev/null | grep -q 'Candidate: (none)'; then \
                    echo "Using apt mirror: ${m}"; \
                    update_ok=1; \
                    break; \
                fi; \
            fi; \
            echo "Mirror ${m} updated index but required packages are unavailable, trying next mirror"; \
        fi; \
        apt-get clean; \
        rm -rf /var/lib/apt/lists/*; \
    done \
    && test "$update_ok" = "1" \
    && (apt-get install -y --no-install-recommends build-essential cmake git \
        || (apt-get clean && rm -rf /var/lib/apt/lists/* && apt-get update && apt-get install -y --no-install-recommends build-essential cmake git))

COPY miloco_ai_engine/core /app/miloco_ai_engine/core
COPY third_party /app/third_party
COPY scripts/ai_engine_cuda_build.sh /app/scripts/ai_engine_cuda_build.sh
COPY scripts/ai_engine_cpu_build.sh /app/scripts/ai_engine_cpu_build.sh

#
# Build and package both variants for "GPU preferred, CPU fallback" runtime.
# IMPORTANT: install CPU/GPU outputs into separate prefixes to avoid dependency pollution
# (e.g. CPU lib accidentally linking against ggml-cuda from GPU install).
#
# - CPU prefix: /app/output_cpu
# - GPU prefix: /app/output_gpu
#
RUN set -eux; \
    KEEP_OUTPUT=0 BUILD_DIR=/app/build/ai_engine_cpu OUTPUT_DIR=/app/output_cpu bash /app/scripts/ai_engine_cpu_build.sh; \
    test -f /app/output_cpu/lib/libllama-mico.so; \
    KEEP_OUTPUT=0 BUILD_DIR=/app/build/ai_engine_cuda OUTPUT_DIR=/app/output_gpu bash /app/scripts/ai_engine_cuda_build.sh; \
    test -f /app/output_gpu/lib/libllama-mico.so; \
    # Build-time sanity checks: CPU lib must not depend on CUDA, GPU lib should.
    if LD_LIBRARY_PATH=/app/output_cpu/lib:${LD_LIBRARY_PATH} ldd /app/output_cpu/lib/libllama-mico.so | grep -Eq 'libcuda\.so|libcudart\.so|libcublas'; then \
        echo "ERROR: CPU build unexpectedly depends on CUDA"; \
        LD_LIBRARY_PATH=/app/output_cpu/lib:${LD_LIBRARY_PATH} ldd /app/output_cpu/lib/libllama-mico.so; \
        exit 1; \
    fi; \
    if ! LD_LIBRARY_PATH=/app/output_gpu/lib:${LD_LIBRARY_PATH} ldd /app/output_gpu/lib/libllama-mico.so | grep -Eq 'libcuda\.so|libcudart\.so|libcublas'; then \
        echo "ERROR: GPU build does not show expected CUDA dependencies"; \
        LD_LIBRARY_PATH=/app/output_gpu/lib:${LD_LIBRARY_PATH} ldd /app/output_gpu/lib/libllama-mico.so; \
        exit 1; \
    fi


################################################
# AI Engine Base
################################################
FROM ${BASE_CUDA_RUN_CONTAINER} AS ai_engine-base

# Restate apt mirrors repository.
ARG APT_MIRRORS_URL
ARG APT_FALLBACK_MIRRORS
# Restate PIP index URL.
ARG PIP_INDEX_URL

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

COPY miloco_ai_engine/pyproject.toml /app/miloco_ai_engine/pyproject.toml

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    set -eux \
    && if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then sed -Ei 's/^Components: .*/Components: main universe restricted multiverse/' /etc/apt/sources.list.d/ubuntu.sources; fi \
    && cp /etc/apt/sources.list.d/ubuntu.sources /tmp/ubuntu.sources.template \
    && mirrors="${APT_MIRRORS_URL%/}/ ${APT_FALLBACK_MIRRORS}" \
    && printf '%s\n' \
        'Acquire::Retries "6";' \
        'Acquire::http::Timeout "30";' \
        'Acquire::https::Timeout "30";' \
        'Acquire::ForceIPv4 "true";' \
        > /etc/apt/apt.conf.d/99-miloco-retries \
    && update_ok=0 \
    && for m in $mirrors; do \
        cp /tmp/ubuntu.sources.template /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i "s|http://archive.ubuntu.com/ubuntu/|${m}|g" /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i "s|http://security.ubuntu.com/ubuntu/|${m}|g" /etc/apt/sources.list.d/ubuntu.sources; \
        if apt-get update; then \
            if apt-cache policy python3 2>/dev/null | grep -q 'Candidate: '; then \
                if ! apt-cache policy python3 2>/dev/null | grep -q 'Candidate: (none)'; then \
                    echo "Using apt mirror: ${m}"; \
                    update_ok=1; \
                    break; \
                fi; \
            fi; \
            echo "Mirror ${m} updated index but required packages are unavailable, trying next mirror"; \
        fi; \
        apt-get clean; \
        rm -rf /var/lib/apt/lists/*; \
    done \
    && test "$update_ok" = "1" \
    && (apt-get install -y --no-install-recommends curl python3 python3-pip python3-dev build-essential \
        clinfo \
        ocl-icd-libopencl1 \
        intel-opencl-icd \
        || (apt-get clean && rm -rf /var/lib/apt/lists/* && apt-get update && apt-get install -y --no-install-recommends curl python3 python3-pip python3-dev build-essential clinfo ocl-icd-libopencl1 intel-opencl-icd)) \
    && pip config set global.index-url "${PIP_INDEX_URL}" \
    && pip config set global.timeout 120 \
    && pip install --upgrade --break-system-packages setuptools packaging \
    && pip install --no-build-isolation --break-system-packages "numpy>=1.24.0" Cython \
    && pip install --no-build-isolation --break-system-packages /app/miloco_ai_engine \
    && rm -rf /app/miloco_ai_engine \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*


################################################
# AI Engine
################################################
FROM ai_engine-base AS ai_engine

ENV LD_LIBRARY_PATH=/app/output/lib/cpu:/app/output/lib/gpu:${LD_LIBRARY_PATH}
ENV LLAMA_MICO_LIB_MODE=auto

WORKDIR /app

COPY --from=ai_engine-builder /app/output_cpu /app/output_cpu
COPY --from=ai_engine-builder /app/output_gpu /app/output_gpu

# Put CPU/GPU libs into separate dirs to avoid dependency pollution.
RUN set -eux; \
    mkdir -p /app/output/lib/cpu /app/output/lib/gpu; \
    cp -a /app/output_cpu/lib/. /app/output/lib/cpu/; \
    cp -a /app/output_gpu/lib/. /app/output/lib/gpu/; \
    # keep a "default" name for compatibility (GPU one)
    cp -a /app/output/lib/gpu/libllama-mico.so /app/output/lib/libllama-mico.so; \
    cp -a /app/output/lib/cpu/libllama-mico.so /app/output/lib/libllama-mico-cpu.so
COPY config/ai_engine_config.yaml /app/config/ai_engine_config.yaml
COPY config/prompt_config.yaml /app/config/prompt_config.yaml
COPY miloco_ai_engine /app/miloco_ai_engine
COPY scripts/start_ai_engine.py /app/start_ai_engine.py

# Install project.
# Install project with face recognition extras.
# This is required for /face/analyze (insightface + onnxruntime).
RUN pip install --no-build-isolation --break-system-packages -e "/app/miloco_ai_engine[face]" \
    && pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null || true \
    && pip install --no-cache-dir --break-system-packages "onnxruntime-openvino>=1.19.0" \
    && pip install --no-cache-dir --break-system-packages "openvino>=2025.0.0" \
    && python3 -c "import insightface; import onnxruntime; from openvino import Core; print('face deps ok, ov devices=', Core().available_devices)"

EXPOSE 8001

# Override by docker-compose, this is the default command.
# HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD curl -f "http://127.0.0.1:8001" || exit 1

CMD ["python3", "start_ai_engine.py"]