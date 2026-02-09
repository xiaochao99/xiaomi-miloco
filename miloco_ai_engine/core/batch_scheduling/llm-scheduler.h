/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef LLM_SCHEDULING_H
#define LLM_SCHEDULING_H

#include <unordered_map>

#include "scheduler_task_info.h"
#include "utils/llama-memory-scheduling.h"
#include "utils/mico-common.h"

class LlmScheduler {
  public:
    explicit LlmScheduler(LlamaMicoContext* context);
    ~LlmScheduler();

    void submit_embedding_infer(std::shared_ptr<mtmd_input_chunk> chunk, std::shared_ptr<std::vector<float>>& embeddig,
                                llama_seq_id seq_id);
    void submit_token_infer(llama_batch text_batch);

    void block_waitting_seq(llama_seq_id seq_id);

  private:
    LlamaMicoContext* context_;
    LlamaMemoryScheduler* memory_scheduler_{nullptr};

    mutable std::mutex seq_set_mutex_;
    std::condition_variable finish_condition_;
    std::unordered_map<size_t, size_t> running_seq_;
};
#endif  // LLM_SCHEDULING_H