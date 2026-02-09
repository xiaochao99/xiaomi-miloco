#!/bin/bash
set -euo pipefail
# TODO: Support multi CPU(x86, arm64) and GPU(NVIDIA, AMD, Intel etc.)

PROJECT_CODE="miloco"
# Docker hub: docker.io
# Github container: ghcr.io
DOCKER_REGISTRY="docker.io"
DOCKER_PREFIX="xiaomi"
SCRIPT_NAME="$0"
FUNC_NAME="help"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

function build() {
    # Build Docker image, default tag: dev
    # Usage: $SCRIPT_NAME build [all|ai_engine|backend] [DOCKER_BUILD_PARAMS]
    if [ $# -gt 2 ]; then
        echo "Error: Too many arguments."
        echo "Usage: $SCRIPT_NAME $FUNC_NAME [all|ai_engine|backend] [DOCKER_BUILD_PARAMS]"
        exit 1
    fi
    local image_name="all"
    local image_tag="dev"
    local options=""
    if [ $# -gt 0 ]; then
        image_name="$1"
        options="${@:2}"
    fi
    echo "Building image: $image_name, params: $options"
    case "$image_name" in
        all)
            "$FUNC_NAME" ai_engine $options
            "$FUNC_NAME" backend $options
        ;;
        ai_engine)
            local build_cmd="docker build $options -t $DOCKER_PREFIX/${PROJECT_CODE}-$image_name:$image_tag --target $image_name -f $PROJECT_ROOT/docker/$image_name.cuda.Dockerfile ."
            echo "eval: $build_cmd"
            eval $build_cmd
        ;;
        backend)
            local build_cmd="docker build $options -t $DOCKER_PREFIX/${PROJECT_CODE}-$image_name:$image_tag --target $image_name -f $PROJECT_ROOT/docker/$image_name.Dockerfile ."
            echo "eval: $build_cmd"
            eval $build_cmd
        ;;
        *)
            echo "Error: Invalid image name: $image_name"
            echo "Usage: $SCRIPT_NAME $FUNC_NAME [all|ai_engine|backend] [DOCKER_BUILD_PARAMS]"
            exit 1
        ;;
    esac
}

function tag() {
    # Usage: tag all|ai_engine|backend [SRC_TAG, default: latest] [DEST_TAG, default: from pyproject.toml]
    if [ $# -gt 3 ]; then
        echo "Error: Too many arguments."
        echo "Usage: $SCRIPT_NAME $FUNC_NAME all|ai_engine|backend [SRC_TAG, default: latest] [DEST_TAG, default: from pyproject.toml]"
        exit 1
    fi
    local image_name="all"
    local source_tag="latest"
    local dest_tag=""
    
    if [ $# -gt 0 ]; then
        image_name="$1"
    fi
    if [ $# -gt 1 ]; then
        source_tag="$2"
    fi
    
    if [[ "$image_name" == "all" || "$image_name" == "ai_engine" ]]; then
        # ai_engine
        local image_full_name="${DOCKER_PREFIX}/${PROJECT_CODE}-ai_engine"
        if [ $# -gt 2 ]; then
            dest_tag="$3"
        else
            dest_tag=$(grep -E '^version\s*=' "$PROJECT_ROOT/miloco_ai_engine/pyproject.toml" | head -n1 | sed -E 's/^version\s*=\s*"(.*)"/\1/')
            dest_tag="v${dest_tag#v}"
        fi
        echo "Tagging image: $image_full_name, source tag: $source_tag, dest tag: $dest_tag"
        if ! docker image inspect "$image_full_name:$source_tag" >/dev/null 2>&1; then
            echo "Error: Image $image_full_name:$source_tag not found."
            exit 1
        fi
        docker tag "$image_full_name:$source_tag" "$image_full_name:$dest_tag"
        # List docker images.
        echo "List docker images: "
        docker images --filter=reference="$image_full_name*"
    fi
    
    if [[ "$image_name" == "all" || "$image_name" == "backend" ]]; then
        # backend
        local image_full_name="${DOCKER_PREFIX}/${PROJECT_CODE}-backend"
        if [ $# -gt 2 ]; then
            dest_tag="$3"
        else
            dest_tag=$(grep -E '^version\s*=' "$PROJECT_ROOT/miloco_server/pyproject.toml" | head -n1 | sed -E 's/^version\s*=\s*"(.*)"/\1/')
            dest_tag="v${dest_tag#v}"
        fi
        echo "Tagging image: $image_full_name, source tag: $source_tag, dest tag: $dest_tag"
        if ! docker image inspect "$image_full_name:$source_tag" >/dev/null 2>&1; then
            echo "Error: Image $image_full_name:$source_tag not found."
            exit 1
        fi
        docker tag "$image_full_name:$source_tag" "$image_full_name:$dest_tag"
        # List docker images.
        echo "List docker images: "
        docker images --filter=reference="$image_full_name*"
    fi
}

function push() {
    # Push Docker images to registry, supports custom registry including GitHub
    # Usage: push [all|ai_engine|backend] [TAG, default: latest] [REGISTRY, default: docker.io] [OPTIONS]
    local image_name="all"
    local image_tag="latest"
    local registry="${DOCKER_REGISTRY}"
    local options=""
    
    if [ $# -gt 0 ]; then
        image_name="$1"
    fi
    if [ $# -gt 1 ]; then
        image_tag="$2"
    fi
    if [ $# -gt 2 ]; then
        registry="$3"
    fi
    if [ $# -gt 3 ]; then
        options="${@:4}"
    fi
    
    # Remove trailing slash from registry if present
    registry="${registry%/}"
    # Determine if we need to add registry prefix
    local registry_prefix=""
    if [[ "$registry" != "docker.io" ]] && [[ "$registry" != "" ]]; then
        registry_prefix="$registry/"
    fi
    
    # Login to registry if credentials are provided via environment variables
    local need_logout=0
    if [[ -n "${DOCKER_HUB_USER:-}" ]] && [[ -n "${DOCKER_HUB_PASSWORD:-}" ]]; then
        echo "Logging in to registry: $registry"
        if echo "$DOCKER_HUB_PASSWORD" | docker login -u "$DOCKER_HUB_USER" --password-stdin "$registry"; then
            echo "Logged in to registry: $registry"
            need_logout=1
        else
            echo "Warning: Failed to login to registry"
        fi
        elif [[ "$registry" == *"ghcr.io"* ]] && [[ -n "${GITHUB_DOCKER_TOKEN:-}" ]]; then
        # Special handling for GitHub Container Registry
        echo "Logging in to GitHub Container Registry"
        if echo "$GITHUB_DOCKER_TOKEN" | docker login ghcr.io -u $GITHUB_DOCKER_USER --password-stdin; then
            echo "Logged in to GitHub Container Registry"
            need_logout=1
        else
            echo "Warning: Failed to login to GitHub Container Registry"
        fi
    fi
    
    # Ensure we logout even if something fails
    trap 'if [[ $need_logout -eq 1 ]]; then docker logout "$registry"; fi' EXIT
    
    case "$image_name" in
        all)
            "$FUNC_NAME" ai_engine "$image_tag" "$registry" $options
            "$FUNC_NAME" backend "$image_tag" "$registry" $options
        ;;
        ai_engine|backend)
            local image_full_name="$DOCKER_PREFIX/$image_name"
            local target_image="$registry_prefix$image_full_name:$image_tag"
            
            # For GitHub Container Registry, image names should be lowercase
            if [[ "$registry" == *"ghcr.io"* ]]; then
                target_image="$registry_prefix$(echo "$DOCKER_PREFIX" | tr '[:upper:]' '[:lower:]')/$image_name:$image_tag"
                image_full_name="$(echo "$DOCKER_PREFIX" | tr '[:upper:]' '[:lower:]')/$image_name"
            fi
            
            # First tag the image for the target registry if needed
            if [[ "$registry_prefix" != "" ]]; then
                echo "Tagging $DOCKER_PREFIX/$image_name:$image_tag for registry: $target_image"
                docker tag "$DOCKER_PREFIX/$image_name:$image_tag" "$target_image"
            fi
            
            # Push the image
            echo "Pushing Docker images: $target_image, Options: $options"
            docker push $options "$target_image"
        ;;
        *)
            echo "Error: Invalid image name: $image_name"
            echo "Usage: $SCRIPT_NAME $FUNC_NAME [all|ai_engine|backend] [REGISTRY] [TAG] [OPTIONS]"
            exit 1
        ;;
    esac
    
    # Logout from registry
    if [[ $need_logout -eq 1 ]]; then
        docker logout "$registry"
        echo "Logged out from registry: $registry"
        need_logout=0
    fi
    
    # Remove the trap
    trap - EXIT
}

function save() {
    # Save Docker images to tar files
    # Usage: save [all|ai_engine|backend] [TAG, default: latest] [OUTPUT_DIR, default: ../docker]
    local image_name="all"
    local output_dir="$PROJECT_ROOT/docker"
    local image_tag="latest"
    
    if [ $# -gt 0 ]; then
        image_name="$1"
    fi
    if [ $# -gt 1 ]; then
        image_tag="$2"
    fi
    if [ $# -gt 2 ]; then
        output_dir="$3"
    fi
    
    # Create output directory if it doesn't exist
    mkdir -p "$output_dir"
    
    case "$image_name" in
        all)
            "$FUNC_NAME" ai_engine "$image_tag" "$output_dir"
            "$FUNC_NAME" backend "$image_tag" "$output_dir"
        ;;
        ai_engine|backend)
            local image_full_name="$DOCKER_PREFIX/$image_name"
            local output_file="$output_dir/${image_full_name//\//_}_$image_tag.tar"
            
            echo "Saving $image_full_name:$image_tag to $output_file"
            if docker image inspect "$image_full_name:$image_tag" >/dev/null 2>&1; then
                docker save -o "$output_file" "$image_full_name:$image_tag"
                echo "Saved successfully: $output_file"
            else
                echo "Error: Image $image_full_name:$image_tag not found."
                exit 1
            fi
        ;;
        *)
            echo "Error: Invalid image name: $image_name"
            echo "Usage: $SCRIPT_NAME $FUNC_NAME [all|ai_engine|backend] [TAG] [OUTPUT_DIR]"
            exit 1
        ;;
    esac
}

function help() {
    # Display help information for all functions
    cat << EOF
Docker Helper Script for ${PROJECT_CODE^^}

Usage: $SCRIPT_NAME <function> [parameters...]

Functions:
  build    Build Docker images
  tag      Tag existing Docker images
  push     Push Docker images to registry
  save     Save Docker images to tar files
  help     Display this help information

Function Details:

build
  Build Docker image, default tag: dev
  Usage: $SCRIPT_NAME build [all|ai_engine|backend] [DOCKER_BUILD_PARAMS]

  Examples:
    $SCRIPT_NAME build                              # Build all images
    $SCRIPT_NAME build ai_engine                    # Build ai_engine image
    $SCRIPT_NAME build backend --no-cache           # Build backend with no cache
    $SCRIPT_NAME build backend "--no-cache --more"  # Build backend with multiple parameters

tag
  Tag existing Docker images
  Usage: $SCRIPT_NAME tag all|ai_engine|backend [SRC_TAG] [DEST_TAG]

  Examples:
    $SCRIPT_NAME tag ai_engine                # Tag ai_engine with version from pyproject.toml
    $SCRIPT_NAME tag backend latest v1.0.0    # Tag backend from latest to v1.0.0

push
  Push Docker images to registry, supports custom registry including GitHub
  Usage: $SCRIPT_NAME push [all|ai_engine|backend] [TAG] [REGISTRY] [OPTIONS]

  Examples:
    $SCRIPT_NAME push                         # Push all images with latest tag to docker.io
    $SCRIPT_NAME push ai_engine v1.0.0        # Push ai_engine v1.0.0 to docker.io
    $SCRIPT_NAME push all latest my-registry.com  # Push all images to custom registry
    $SCRIPT_NAME push backend latest ghcr.io/github_user/repo  # Push to GitHub Container Registry

  Authentication Environment Variables:
    Docker Hub: DOCKER_HUB_USER and DOCKER_HUB_PASSWORD
    GitHub Container Registry: GITHUB_DOCKER_USER and GITHUB_DOCKER_TOKEN

save
  Save Docker images to tar files
  Usage: $SCRIPT_NAME save [all|ai_engine|backend] [TAG] [OUTPUT_DIR]

  Examples:
    $SCRIPT_NAME save                             # Save all images with latest tag to ../docker
    $SCRIPT_NAME save backend dev                 # Save backend dev image to ../docker
    $SCRIPT_NAME save ai_engine prod /tmp/images  # Save ai_engine prod image to /tmp/images

Notes:
  - Default project code: $PROJECT_CODE
  - Default Docker registry: $DOCKER_REGISTRY
EOF
}

if [ $# -lt 1 ]; then
    help
    exit 1
fi
FUNC_NAME="$1"
# Shift past the function name
shift
# Check if function exists
if declare -f "$FUNC_NAME" > /dev/null; then
    "$FUNC_NAME" "$@"
else
    echo "Error: func '$FUNC_NAME' undefined"
    exit 1
fi


