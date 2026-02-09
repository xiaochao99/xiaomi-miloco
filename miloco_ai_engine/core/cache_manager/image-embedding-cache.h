/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef IMAGE_EMBEDDING_CACHE_H
#define IMAGE_EMBEDDING_CACHE_H

#include <algorithm>
#include <unordered_set>

#include "utils/mico-common.h"

// Forward declarations
struct llama_context;
struct llama_model;

struct CacheStats {
    size_t total_entries;  // Total number of cache entries
    size_t hits;           // Number of cache hits
    size_t misses;         // Number of cache misses
    // size_t evictions;           // Number of evicted entries
    size_t total_memory_usage;  // Total memory usage in bytes

    CacheStats() : total_entries(0), hits(0), misses(0), total_memory_usage(0) {}
};

class ImageEmbeddingCache {
  public:
    explicit ImageEmbeddingCache(size_t max_entries, size_t max_mem, LlamaMicoContext* context);
    ~ImageEmbeddingCache();

    std::string prepare(const mtmd_input_chunk* chunk);
    bool store(const mtmd_input_chunk* chunk, const std::vector<float>& embeddings);

    std::shared_ptr<std::vector<float>> lookup(const mtmd_input_chunk* chunk);
    bool waiting(const mtmd_input_chunk* chunk);
    bool storing(const mtmd_input_chunk* chunk);

  private:
    std::string image_hash(const mtmd_input_chunk* chunk);
    // Maintain cache size
    void maintain();
    // Update cache statistics
    void update_stats(bool hit);

    llama_context* context_{nullptr};
    llama_model* model_{nullptr};

    // cache date
    std::unordered_set<std::string> image_wait_set_;
    std::unordered_map<std::string, std::shared_ptr<std::vector<float>>> image_stored_map_;
    std::vector<std::string> embed_order;
    mutable std::mutex cache_mutex_;

    // stats info
    CacheStats stats_;
    std::chrono::steady_clock::time_point last_maintenance_;
    mutable std::mutex stats_mutex_;

    size_t max_memory_usage_{0};  // mb
    size_t max_num_entries_{0};
    int32_t maintenance_interval_{5000};  // ms
};
#endif  // IMAGE_EMBEDDING_CACHE_H