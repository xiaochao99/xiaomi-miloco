cmake_minimum_required(VERSION 3.20)
project(llama_mico LANGUAGES C CXX)

set(LIB_SOURCE_FILES "llama-mico.cpp")

add_library(llama-mico SHARED ${LIB_SOURCE_FILES})

set(THIRD_PARTY_PATH ${PROJECT_SOURCE_DIR}/../../third_party)
set(LLAMA_THIRD_PARTY_PATH ${THIRD_PARTY_PATH}/llama.cpp)

include_directories(${PROJECT_SOURCE_DIR}
                    ${PROJECT_SOURCE_DIR}/utils
                    ${PROJECT_SOURCE_DIR}/cache_manager
                    ${PROJECT_SOURCE_DIR}/batch_scheduling
                    ${LLAMA_THIRD_PARTY_PATH}
                    ${LLAMA_THIRD_PARTY_PATH}/include
                    ${LLAMA_THIRD_PARTY_PATH}/ggml/include
                    ${LLAMA_THIRD_PARTY_PATH}/src
                    ${LLAMA_THIRD_PARTY_PATH}/mutil-modal
                    ${LLAMA_THIRD_PARTY_PATH}/common
                    ${LLAMA_THIRD_PARTY_PATH}/common/vendor)

# Stub for llama_add_compile_flags (required by newer llama.cpp src/CMakeLists.txt)
# The full function lives in cmake/common.cmake but includes relative paths that
# don't resolve correctly when built as a subproject. The flags are only for
# warnings/sanitizers which are not critical for our use case.
function(llama_add_compile_flags)
endfunction()

# LLAMA_INSTALL_VERSION is normally set by top-level llama.cpp CMakeLists.txt from
# git build info. We define a placeholder here since we only build a subdirectory.
set(LLAMA_INSTALL_VERSION 0.0.0)

add_subdirectory(${LLAMA_THIRD_PARTY_PATH}/ggml ${CMAKE_CURRENT_BINARY_DIR}/llama_third_party/ggml)
add_subdirectory(${LLAMA_THIRD_PARTY_PATH}/src  ${CMAKE_CURRENT_BINARY_DIR}/llama_third_party/src)

target_link_libraries(llama-mico PRIVATE llama ggml)

# Link CUDA backend if enabled
if (GGML_CUDA)
    target_link_libraries(llama-mico PRIVATE ggml-cuda)
endif()

add_subdirectory(utils)
add_subdirectory(cache_manager)
add_subdirectory(batch_scheduling)
# add_subdirectory(mutil-modal)


install(TARGETS llama-mico DESTINATION lib)