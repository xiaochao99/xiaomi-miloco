/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef ENCODER_SCHEDULING_H
#define ENCODER_SCHEDULING_H
#include <memory>

#include "cache_manager/image-embedding-cache.h"

class EncoderSheduler {
  public:
    explicit EncoderSheduler(LlamaMicoContext* context, int32_t max_entries = 100, int32_t max_memory_mb = 1024);
    ~EncoderSheduler();

    std::shared_ptr<ImageEmbeddingCache> get_cache() { return encode_cache_; }

    void submit_encoder_task(std::shared_ptr<mtmd_input_chunk> chunk);

    std::shared_ptr<std::vector<float>> wait_for_result(std::shared_ptr<mtmd_input_chunk> chunk);

    std::shared_ptr<std::vector<float>> blocking_encoder(std::shared_ptr<mtmd_input_chunk> chunk);

  private:
    void encoder_task(std::shared_ptr<mtmd_input_chunk> chunk);
    void process_encoder();

    LlamaMicoContext* context_;

    std::atomic<bool> stop_flag_{false};
    std::thread* encoder_thread_;

    mutable std::mutex encoder_queue_mutex_;
    std::queue<std::function<void()>> encoder_queue_;
    std::condition_variable encode_condition_;  // for encode thread
    std::condition_variable encode_finish_condition_;

    std::shared_ptr<ImageEmbeddingCache> encode_cache_{nullptr};
};

#endif  // ENCODER_SCHEDULING_H