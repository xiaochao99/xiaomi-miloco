/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "chunk-infer-cache.h"
#define EMTRIES_PROPORTION_LIMIT 0.8f

ChunkInferCache::ChunkInferCache(size_t max_cache_seq, LlamaMicoContext* context)
    : context_(context->lctx), model_(context->model) {
    memory_scheduler_ = static_cast<LlamaMemoryScheduler*>(context->memory_scheduler);
    size_t seq_max = llama_n_seq_max(context_);
    int32_t cache_seq_begin = seq_max - max_cache_seq;
    if (cache_seq_begin < 0) {
        LOG_ERR("Cache size is set too large, must be much smaller than seq_max\n");
        exit(1);
    }

    std::lock_guard<std::mutex> lock(cache_mutex_);
    for (size_t i = cache_seq_begin; i < seq_max; ++i) use_seq_mem_[i] = std::make_shared<SeqEntryList>(i);
}

ChunkInferCache::~ChunkInferCache() {
    std::lock_guard<std::mutex> lock(cache_mutex_);
    cache_map_.clear();
    LOG_INF("Chunk infer cache destroyed\n");
}

bool ChunkInferCache::prepare(std::string& chunk_hash) {
    std::lock_guard<std::mutex> lock(cache_mutex_);
    if (cache_wait_set_.count(chunk_hash) > 0) return false;  // already in wait
    if (cache_map_.count(chunk_hash) > 0) return false;       // already in stored
    cache_wait_set_.insert(chunk_hash);
    return true;
}

void ChunkInferCache::unprepared(std::string& chunk_hash) {
    std::unique_lock<std::mutex> cache_lock(cache_mutex_);
    if (cache_wait_set_.count(chunk_hash) > 0) cache_wait_set_.erase(chunk_hash);  // remove from wait set
    stored_condition_.notify_all();
}

bool ChunkInferCache::store(std::vector<std::string> chunk_hashs, size_t chunk_id, llama_seq_id seq_id,
                            llama_token last_token, int32_t n_past) {
    maintain();  // Try to clean cache

    std::unique_lock<std::mutex> cache_lock(cache_mutex_);
    if (cache_wait_set_.count(chunk_hashs[chunk_id]) > 0)
        cache_wait_set_.erase(chunk_hashs[chunk_id]);  // Remove from wait set
    stored_condition_.notify_all();                    // NOTE: cache_lock controls stored_condition_

    std::vector<std::shared_ptr<CacheEntry>> pre_entries;
    std::vector<size_t> pre_chunk_indexs;

    for (size_t i = 0; i <= chunk_id; ++i) {
        std::string chunk_hash = chunk_hashs[i];
        auto it = cache_map_.find(chunk_hash);
        if (it != cache_map_.end()) {
            auto entry = it->second;
            pre_entries.push_back(entry);
            pre_chunk_indexs.push_back(i);
        }
    }

    if (!pre_chunk_indexs.empty() && pre_chunk_indexs.back() == chunk_id) return true;  // has cached

    std::shared_ptr<SeqEntryList> target_seq = nullptr;

    if (!pre_entries.empty()) {
        for (auto m : use_seq_mem_) {
            auto seq_entries = m.second->seq_entries;
            if (seq_entries.empty()) continue;

            if (seq_entries.back() == pre_entries.back()) {
                target_seq = m.second;
            }
        }
    }
    if (target_seq == nullptr) {  // New sequence
        for (auto m : use_seq_mem_) {
            if (m.second->seq_entries.empty()) target_seq = m.second;
        }
    }
    if (target_seq == nullptr) {
        return false;
    }

    auto entry = std::make_shared<CacheEntry>();
    entry->prompt_hash = chunk_hashs[chunk_id];
    entry->pos_begin =
        pre_entries.empty() ? 0 : pre_entries.back()->pos_end;  // NOTE: May have misalignment issue later
    entry->pos_end = n_past;
    entry->last_token = last_token;
    entry->reference_count = 1;

    if (!serialize_kv_cache_state(seq_id, target_seq->cache_seq_id, target_seq->last_pos)) {
        LOG_WRN("store: empty kv_cache_state, not storing");
        return false;
    }

    if (target_seq->seq_entries.empty()) {
        for (auto& e : pre_entries) e->reference_count++;
        pre_entries.push_back(entry);
        target_seq->seq_entries.insert(target_seq->seq_entries.end(), pre_entries.begin(), pre_entries.end());
    } else {
        target_seq->seq_entries.push_back(entry);
    }

    target_seq->last_pos = n_past;
    target_seq->last_access = std::chrono::steady_clock::now();
    cache_map_[chunk_hashs[chunk_id]] = entry;

    LOG_INF("Stored KV cache entry with key: %s, use cache_room: %d, npast: %d\n", chunk_hashs[chunk_id].c_str(),
            target_seq->cache_seq_id, target_seq->last_pos);

    return true;
}

std::shared_ptr<CacheEntry> ChunkInferCache::lookup(std::string chunk_hash) {
    std::lock_guard<std::mutex> lock(cache_mutex_);

    auto it = cache_map_.find(chunk_hash);
    if (it == cache_map_.end()) return nullptr;
    auto entry = it->second;

    if (entry->reference_count != 1) return entry;
    // Need to maintain unique reference
    for (auto& seq : use_seq_mem_) {
        for (const auto& e : seq.second->seq_entries)
            if (e == entry) seq.second->last_access = std::chrono::steady_clock::now();
    }
    // LOG_INF("hit KV cache entry with key: %s\n", chunk_hash.c_str());
    return entry;
}

bool ChunkInferCache::apply_cache_entry(const std::shared_ptr<CacheEntry>& entry, llama_seq_id target_seq_id) {
    if (!entry) return false;
    llama_seq_id src_seq_id = -1;
    for (auto& seq : use_seq_mem_) {
        for (const auto& e : seq.second->seq_entries)
            if (e == entry) {
                src_seq_id = seq.first;
                break;
            }
    }

    if (src_seq_id == -1) return false;
    return deserialize_kv_cache_state(src_seq_id, target_seq_id, entry->pos_end);
}

bool ChunkInferCache::waiting(std::string chunk_hash) {
    std::lock_guard<std::mutex> lock(cache_mutex_);
    return cache_wait_set_.count(chunk_hash) > 0;
}

bool ChunkInferCache::storing(std::string chunk_hash) {
    std::lock_guard<std::mutex> lock(cache_mutex_);
    return cache_map_.count(chunk_hash) > 0;
}

void ChunkInferCache::block_waiting(std::string chunk_hash) {
    std::unique_lock<std::mutex> lock(cache_mutex_);
    if (cache_wait_set_.count(chunk_hash) == 0) return;
    stored_condition_.wait(lock, [this, chunk_hash]() { return cache_wait_set_.count(chunk_hash) == 0; });
}

void ChunkInferCache::block_waiting_and_prepare(std::string chunk_hash) {
    std::unique_lock<std::mutex> lock(cache_mutex_);
    if (cache_wait_set_.count(chunk_hash) > 0)
        stored_condition_.wait(lock, [this, chunk_hash]() { return cache_wait_set_.count(chunk_hash) == 0; });

    if (cache_map_.count(chunk_hash) == 0) cache_wait_set_.insert(chunk_hash);  // Enter prepare state if not completed
}

void ChunkInferCache::maintain() {
    auto now = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(cache_mutex_);

    size_t used_seq_num = 0;
    for (auto& seq : use_seq_mem_)
        if (!seq.second->seq_entries.empty()) used_seq_num++;
    float limit = EMTRIES_PROPORTION_LIMIT;
    size_t max_seq_num = use_seq_mem_.size() * limit;
    int32_t delete_num = (int32_t)used_seq_num - (int32_t)max_seq_num;
    if (used_seq_num < use_seq_mem_.size()) return;

    // Find sequences to delete
    std::vector<std::pair<size_t, std::shared_ptr<SeqEntryList>>> sorted_seqs;
    for (auto& seq : use_seq_mem_) {
        if (!seq.second->seq_entries.empty()) {
            sorted_seqs.push_back(seq);
        }
    }
    std::sort(sorted_seqs.begin(), sorted_seqs.end(),
              [](const std::pair<size_t, std::shared_ptr<SeqEntryList>>& a,
                 const std::pair<size_t, std::shared_ptr<SeqEntryList>>& b) {
                  return a.second->last_access < b.second->last_access;
              });
    std::vector<size_t> to_delete;
    for (size_t i = 0; i < delete_num && i < sorted_seqs.size(); ++i) {
        to_delete.push_back(sorted_seqs[i].first);
    }

    // Find entries to delete
    std::vector<std::string> to_delete_keys;
    for (size_t seq_id : to_delete) {
        auto it = use_seq_mem_.find(seq_id);
        if (it != use_seq_mem_.end()) {
            for (auto& entry : it->second->seq_entries) {
                entry->reference_count--;
                if (entry->reference_count <= 0) to_delete_keys.push_back(entry->prompt_hash);
            }
            it->second->seq_entries.clear();
            it->second->last_pos = 0;
            memory_scheduler_->submit_clear_mem(seq_id, -1, -1);
            LOG_INF("maintain deleted sequence %zu from cache\n", seq_id);
        }
    }

    for (auto& key : to_delete_keys) cache_map_.erase(key);
}

bool ChunkInferCache::serialize_kv_cache_state(llama_seq_id src_seq_id, llama_seq_id dst_seq_id, llama_pos pos_begin) {
    memory_scheduler_->submit_cache_mem(src_seq_id, dst_seq_id, pos_begin, -1);
    return true;
}

bool ChunkInferCache::deserialize_kv_cache_state(llama_seq_id src_seq_id, llama_seq_id dst_seq_id, llama_pos pos_end) {
    memory_scheduler_->submit_cache_mem(src_seq_id, dst_seq_id, -1, pos_end);
    return true;
}