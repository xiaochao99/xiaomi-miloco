/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef CHUNK_HASH_H
#define CHUNK_HASH_H

#include <cstdint>
#include <iomanip>
#include <ios>
#include <string>

#include "mutil-modal/mtmd.h"

// Simple hash function for strings
uint64_t simple_hash(const std::string& str);

// Convert hash to hex string
std::string hash_to_hex(uint64_t hash);

std::string get_chunk_description(const mtmd_input_chunk* chunk);

std::vector<std::string> chunk_hashs(mtmd::input_chunks* input_chunks);

#endif  // CHUNK_HASH_H