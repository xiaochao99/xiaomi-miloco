/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "llama-memory-scheduling.h"

#include <iostream>

LlamaMemoryScheduler::LlamaMemoryScheduler(const llama_context* ctx) : thread_(nullptr) {
    memory_ = llama_get_memory(ctx);
    thread_ = new std::thread(&LlamaMemoryScheduler::process, this);
}

LlamaMemoryScheduler::~LlamaMemoryScheduler() {
    stop_flag_.store(true);
    condition_.notify_one();
    if (thread_ && thread_->joinable()) {
        thread_->join();
        delete thread_;
        thread_ = nullptr;
    }
}

void LlamaMemoryScheduler::submit_clear_mem(size_t seq_id, llama_pos p0, llama_pos p1) {
    {
        std::lock_guard<std::mutex> lock(task_queue_mutex_);
        std::function<void()> task = [this, seq_id, p0, p1]() { llama_memory_seq_rm(memory_, seq_id, p0, p1); };
        tasks_.push(task);
    }
    condition_.notify_one();
}

void LlamaMemoryScheduler::submit_cache_mem(size_t src_seq_id, size_t dest_seq_id, llama_pos p0, llama_pos p1) {
    {
        std::lock_guard<std::mutex> lock(task_queue_mutex_);
        std::function<void()> task = [this, src_seq_id, dest_seq_id, p0, p1]() {
            llama_pos max_pos = llama_memory_seq_pos_max(memory_, dest_seq_id);
            llama_pos p_0 = std::max(p0, max_pos + 1);

            if (p_0 <= p1 || p1 == -1) llama_memory_seq_cp(memory_, src_seq_id, dest_seq_id, p_0, p1);
        };
        tasks_.push(task);
    }
    condition_.notify_one();
}

void LlamaMemoryScheduler::submit_function_use_mem(std::function<void()> func) {
    {
        std::lock_guard<std::mutex> lock(task_queue_mutex_);
        tasks_.push(func);
    }
    condition_.notify_one();
}

void LlamaMemoryScheduler::process() {
    while (true) {
        std::function<void()> task = nullptr;

        {  // lock task_queue_mutex
            std::unique_lock<std::mutex> lock(task_queue_mutex_);
            condition_.wait(lock, [this] { return !tasks_.empty() || stop_flag_.load(); });
            if (stop_flag_.load()) {
                break;
            }
            task = std::move(tasks_.front());
            tasks_.pop();
        }

        if (task == nullptr) continue;  // Skip if task is null

        try {
            task();
        } catch (const std::exception& e) {
            LOG_ERR("failed to use llama api\n");
        }
    }
}
