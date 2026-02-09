/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef CHUNK_INFER_CACHE_H
#define CHUNK_INFER_CACHE_H
#include <unordered_set>

#include "utils/mico-common.h"

// Forward declarations
struct llama_context;
struct llama_model;

struct CacheEntry {
    std::string prompt_hash;
    // pos[pos_begin, pos_end)
    llama_pos pos_begin;
    llama_pos pos_end;  // n_past
    llama_token last_token;

    int32_t reference_count;

    CacheEntry() : reference_count(0), pos_begin{-1}, pos_end{-1}, last_token{-1} {}
};

struct SeqEntryList {
    int32_t cache_seq_id;
    llama_pos last_pos;  // n_past
    std::vector<std::shared_ptr<CacheEntry>> seq_entries;

    std::chrono::steady_clock::time_point last_access;  // Last access time

    SeqEntryList(int32_t seq_id) : cache_seq_id(seq_id), last_pos(0) {}
};

class ChunkInferCache {
  public:
    ChunkInferCache(size_t max_cache_seq, LlamaMicoContext* context);
    ~ChunkInferCache();

    bool prepare(std::string& chunk_hash);
    void unprepared(std::string& chunk_hash);

    bool store(std::vector<std::string> chunk_hashs, size_t chunk_id, llama_seq_id seq_id, llama_token last_token,
               int32_t n_past);

    std::shared_ptr<CacheEntry> lookup(std::string chunk_hash);
    bool apply_cache_entry(const std::shared_ptr<CacheEntry>& entry, llama_seq_id target_seq_id);

    bool waiting(std::string chunk_hash);
    bool storing(std::string chunk_hash);

    void block_waiting(std::string chunk_hash);
    void block_waiting_and_prepare(std::string chunk_hash);

  private:
    bool serialize_kv_cache_state(llama_seq_id src_seq_id, llama_seq_id dst_seq_id, llama_pos pos_begin);
    bool deserialize_kv_cache_state(llama_seq_id src_seq_id, llama_seq_id dst_seq_id, llama_pos pos_end);

    // Maintain cache size
    void maintain();

    llama_context* context_;
    llama_model* model_;
    LlamaMemoryScheduler* memory_scheduler_;

    std::unordered_set<std::string> cache_wait_set_;
    std::unordered_map<std::string, std::shared_ptr<CacheEntry>> cache_map_;
    std::unordered_map<size_t, std::shared_ptr<SeqEntryList>> use_seq_mem_;
    mutable std::mutex cache_mutex_;
    std::condition_variable stored_condition_;
};

#endif  // CHUNK_INFER_CACHE_H