/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "chunk-hash.h"

#include <sstream>
#include <vector>

uint64_t simple_hash(const std::string& str) {
    uint64_t hash = 0x811c9dc5;
    for (char c : str) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 0x01000193;
    }
    return hash;
}

std::string hash_to_hex(uint64_t hash) {
    std::stringstream ss;
    ss << std::hex << std::setfill('0') << std::setw(16) << hash;
    return ss.str();
}

std::string get_chunk_description(const mtmd_input_chunk* chunk) {
    std::stringstream ss;
    if (chunk == nullptr) return "";

    if (mtmd_input_chunk_get_type(chunk) == MTMD_INPUT_CHUNK_TYPE_TEXT) {
        size_t n_tokens;
        const llama_token* tokens = mtmd_input_chunk_get_tokens_text(chunk, &n_tokens);
        if (tokens && n_tokens > 0) {
            for (size_t j = 0; j < n_tokens; ++j) {
                ss << tokens[j] << ",";
            }
        }
    } else if (mtmd_input_chunk_get_type(chunk) == MTMD_INPUT_CHUNK_TYPE_IMAGE) {
        // For images, we use the image ID as part of the hash
        const mtmd_image_tokens* image_tokens = mtmd_input_chunk_get_tokens_image(chunk);
        if (image_tokens) {
            const char* id = mtmd_image_tokens_get_id(image_tokens);
            ss << "IMG:" << id << ",";
        }
    }
    return ss.str();
}

std::vector<std::string> chunk_hashs(mtmd::input_chunks* input_chunks) {
    std::vector<std::string> hashes;
    std::string prompt_string = "";
    for (size_t i = 0; i < input_chunks->size(); ++i) {
        const mtmd_input_chunk* chunk = (*input_chunks)[i];
        prompt_string += get_chunk_description(chunk);
        hashes.push_back(hash_to_hex(simple_hash(prompt_string)));
    }
    return hashes;
}