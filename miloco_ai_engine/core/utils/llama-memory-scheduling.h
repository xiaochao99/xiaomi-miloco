/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef MEMORY_SCHEDULER_H
#define MEMORY_SCHEDULER_H

#include <atomic>
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <vector>

#include "common/log.h"
#include "llama.h"

class LlamaMemoryScheduler {
  public:
    LlamaMemoryScheduler(const llama_context* ctx);
    ~LlamaMemoryScheduler();

    void submit_clear_mem(size_t seq_id, llama_pos p0, llama_pos p1);
    void submit_cache_mem(size_t src_seq_id, size_t dest_seq_id, llama_pos p0, llama_pos p1);
    void submit_function_use_mem(std::function<void()> func);

    // Delete copy and move constructors/assignment
    LlamaMemoryScheduler(const LlamaMemoryScheduler&) = delete;
    LlamaMemoryScheduler& operator=(const LlamaMemoryScheduler&) = delete;
    LlamaMemoryScheduler(LlamaMemoryScheduler&&) = delete;
    LlamaMemoryScheduler& operator=(LlamaMemoryScheduler&&) = delete;

  private:
    void process();
    llama_memory_t memory_;
    std::atomic<bool> stop_flag_{false};
    mutable std::mutex task_queue_mutex_;
    std::condition_variable condition_;
    std::queue<std::function<void()>> tasks_;
    std::thread* thread_;
};

#endif  // MEMORY_SCHEDULER_H
