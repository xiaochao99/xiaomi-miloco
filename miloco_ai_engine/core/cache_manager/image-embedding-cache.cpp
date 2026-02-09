/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "image-embedding-cache.h"
#define EMTRIES_PROPORTION_LIMIT 0.8

ImageEmbeddingCache::ImageEmbeddingCache(size_t max_entries, size_t max_mem, LlamaMicoContext* context)
    : context_(context->lctx), model_(context->model), last_maintenance_(std::chrono::steady_clock::now()) {
    LOG_INF("Image encode cache initialized with max_entries=%zu, max_memory_mb=%zu\n", max_entries, max_mem);
    max_num_entries_ = max_entries;
    max_memory_usage_ = max_mem;
}

ImageEmbeddingCache::~ImageEmbeddingCache() {
    std::lock_guard<std::mutex> lock(cache_mutex_);
    image_wait_set_.clear();
    image_stored_map_.clear();
    embed_order.clear();

    LOG_INF("Image embedding cache destroyed\n");
}

std::string ImageEmbeddingCache::image_hash(const mtmd_input_chunk* chunk) {
    std::string res = "";

    if (!chunk) return res;

    if (mtmd_input_chunk_get_type(chunk) != MTMD_INPUT_CHUNK_TYPE_IMAGE) return res;

    const mtmd_image_tokens* image_tokens = mtmd_input_chunk_get_tokens_image(chunk);
    if (!image_tokens) return res;

    res = mtmd_image_tokens_get_id(image_tokens);
    return res;
}

std::string ImageEmbeddingCache::prepare(const mtmd_input_chunk* chunk) {
    std::string res = image_hash(chunk);
    if (res.empty()) return res;

    std::lock_guard<std::mutex> lock(cache_mutex_);
    if (image_wait_set_.count(res) > 0) return "";    // already in wait
    if (image_stored_map_.count(res) > 0) return "";  // already in stored
    image_wait_set_.insert(res);
    return res;
}

bool ImageEmbeddingCache::store(const mtmd_input_chunk* chunk, const std::vector<float>& embeddings) {
    std::string key = image_hash(chunk);
    if (key.empty()) return false;

    maintain();  // Try to clean cache

    std::unique_lock<std::mutex> cache_lock(cache_mutex_, std::defer_lock);
    std::unique_lock<std::mutex> stats_lock(stats_mutex_, std::defer_lock);
    auto now = std::chrono::steady_clock::now();

    auto embd_ptr = std::make_shared<std::vector<float>>(embeddings);
    cache_lock.lock();
    image_stored_map_[key] = embd_ptr;
    image_wait_set_.erase(key);

    // Update order
    auto order_it = std::find(embed_order.begin(), embed_order.end(), key);
    if (order_it != embed_order.end()) {
        embed_order.erase(order_it);
    }
    embed_order.push_back(key);

    stats_lock.lock();
    stats_.total_entries += 1;
    stats_.total_memory_usage += embeddings.size() * sizeof(float);
    stats_lock.unlock();

    cache_lock.unlock();

    return true;
}

std::shared_ptr<std::vector<float>> ImageEmbeddingCache::lookup(const mtmd_input_chunk* chunk) {
    std::string key = image_hash(chunk);
    if (key.empty()) {
        LOG_INF("Image hash is empty %p\n", chunk);
        return nullptr;
    }

    std::lock_guard<std::mutex> cache_lock(cache_mutex_);
    auto it = image_stored_map_.find(key);
    if (it != image_stored_map_.end()) {  // hit
        auto key = it->first;
        // Update order
        auto order_it = std::find(embed_order.begin(), embed_order.end(), key);
        if (order_it != embed_order.end()) {
            embed_order.erase(order_it);
            embed_order.push_back(key);
        } else {
            // exit(!)
        }

        update_stats(true);
        // LOG_INF("Image embeddings hit for hash: %s\n", (key).c_str());
        return it->second;
    }

    update_stats(false);
    return nullptr;
}

bool ImageEmbeddingCache::waiting(const mtmd_input_chunk* chunk) {
    std::string key = image_hash(chunk);
    if (key.empty()) return false;
    std::lock_guard<std::mutex> cache_lock(cache_mutex_);
    return image_wait_set_.count(key) > 0;
}

bool ImageEmbeddingCache::storing(const mtmd_input_chunk* chunk) {
    std::string key = image_hash(chunk);
    if (key.empty()) return false;
    std::lock_guard<std::mutex> cache_lock(cache_mutex_);
    return image_stored_map_.count(key) > 0;
}

void ImageEmbeddingCache::maintain() {
    auto now = std::chrono::steady_clock::now();

    std::unique_lock<std::mutex> cache_lock(cache_mutex_, std::defer_lock);
    std::unique_lock<std::mutex> stats_lock(stats_mutex_, std::defer_lock);

    bool need_maintain = true;
    stats_lock.lock();
    auto time_since_maintenance = std::chrono::duration_cast<std::chrono::microseconds>(now - last_maintenance_);
    size_t max_memory_byte = max_memory_usage_ * 1024 * 1024;  // MB to byte
    size_t total_memory_usage = stats_.total_memory_usage;
    size_t total_entries = stats_.total_entries;

    if (time_since_maintenance.count() < maintenance_interval_) need_maintain &= false;
    if (total_entries < max_num_entries_ && total_memory_usage < max_memory_byte) need_maintain &= false;
    stats_lock.unlock();

    if (!need_maintain) return;

    float max_entries_proportion = EMTRIES_PROPORTION_LIMIT;
    int32_t target_entries = max_num_entries_ * max_entries_proportion;
    int32_t target_memory_usage = max_memory_usage_ * max_entries_proportion * 1024 * 1024;  // MB to byte
    cache_lock.lock();
    while (total_entries > target_entries || total_memory_usage > target_memory_usage) {
        auto it = embed_order.begin();
        if (it == embed_order.end()) break;
        auto key = (*it);
        auto value = image_stored_map_[key];
        size_t byte_size = 0;
        if (value) byte_size = image_stored_map_[key]->size() * sizeof(float);
        LOG_INF("Evicted image embeddings for hash: %s, remaining size: %zu\n", (key).c_str(), byte_size);
        image_stored_map_.erase(key);
        embed_order.erase(it);

        total_memory_usage -= byte_size;
        total_entries -= 1;
    }

    // Prevent cache update
    stats_lock.lock();
    stats_.total_memory_usage = total_memory_usage;
    stats_.total_entries = embed_order.size();
    last_maintenance_ = now;
    stats_lock.unlock();

    cache_lock.unlock();
}

void ImageEmbeddingCache::update_stats(bool hit) {
    std::lock_guard<std::mutex> stats_lock(stats_mutex_);
    if (hit)
        stats_.hits++;
    else
        stats_.misses++;

    // todo update stats
}
