/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef BATCH_SCHEDULER_H
#define BATCH_SCHEDULER_H

#include "cache_manager/chunk-infer-cache.h"
#include "common/chat.h"
#include "common/json-partial.h"
#include "common/log.h"
#include "encoder-scheduler.h"
#include "llama.h"
#include "llm-scheduler.h"
#include "scheduler_task_info.h"
#include "utils/chunk-hash.h"
#include "utils/llama-memory-scheduling.h"

class BatchScheduler {
  public:
    explicit BatchScheduler(LlamaMicoContext* context, size_t batch_time_wait = 5);
    ~BatchScheduler();

    void blocking_infer(std::shared_ptr<mtmd::input_chunks> input_chunks, size_t chat_cmpl_id, int32_t priority = 0);

  private:
    void process_batch();
    void process_text_batch(std::vector<std::shared_ptr<SycChunkTask>> text_buffer);
    void process_image_batch(std::vector<std::shared_ptr<SycChunkTask>> image_buffer);

    LlamaMicoContext* context_{nullptr};

    std::unique_ptr<EncoderSheduler> encoder_scheduler_{nullptr};
    std::unique_ptr<LlmScheduler> llm_scheduler_{nullptr};

    std::unique_ptr<ChunkInferCache> kv_cache_{nullptr};

    std::thread* scheduler_thread_{nullptr};
    std::atomic<bool> stop_flag_{false};

    mutable std::mutex task_queue_mutex_;
    std::condition_variable task_condition_;
    std::condition_variable finish_condition_;

    std::priority_queue<std::shared_ptr<SycChunkTask>> task_queue_;

    int32_t text_batch_size_{512};  // token size
    int32_t image_batch_size_{1};   // token size
    size_t time_wait_{3};           // ms
};

#endif  // BATCH_SCHEDULER_H