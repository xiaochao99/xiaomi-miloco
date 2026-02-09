/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "encoder-scheduler.h"

EncoderSheduler::EncoderSheduler(LlamaMicoContext* context, int32_t max_entries, int32_t max_memory_mb)
    : context_(context) {
    // encoder cache
    encode_cache_ = std::make_unique<ImageEmbeddingCache>(max_entries, max_memory_mb, context);
    encoder_thread_ = new std::thread(&EncoderSheduler::process_encoder, this);
}

EncoderSheduler::~EncoderSheduler() {
    stop_flag_.store(true);
    encode_condition_.notify_one();
    if (encoder_thread_) {
        encoder_thread_->join();
        delete encoder_thread_;
    }
}

void EncoderSheduler::submit_encoder_task(std::shared_ptr<mtmd_input_chunk> chunk) {
    std::function<void()> task = [this, chunk]() {
        encoder_task(chunk);
        encode_finish_condition_.notify_all();
    };

    std::unique_lock<std::mutex> queue_lock(encoder_queue_mutex_);
    std::string key = encode_cache_->prepare(chunk.get());  // Blocking stage placeholder
    if (key.empty()) return;
    encoder_queue_.push(task);
    encode_condition_.notify_one();
}

std::shared_ptr<std::vector<float>> EncoderSheduler::wait_for_result(std::shared_ptr<mtmd_input_chunk> chunk) {
    std::unique_lock<std::mutex> queue_lock(encoder_queue_mutex_);  // tmp lock
    encode_finish_condition_.wait(queue_lock, [this, chunk] { return !encode_cache_->waiting(chunk.get()); });
    auto res = encode_cache_->lookup(chunk.get());
    return res;
}

std::shared_ptr<std::vector<float>> EncoderSheduler::blocking_encoder(std::shared_ptr<mtmd_input_chunk> chunk) {
    submit_encoder_task(chunk);
    return wait_for_result(chunk);
}

void EncoderSheduler::encoder_task(std::shared_ptr<mtmd_input_chunk> chunk) {
    auto chunk_type = mtmd_input_chunk_get_type(chunk.get());
    if (chunk_type != MTMD_INPUT_CHUNK_TYPE_IMAGE) return;

    int64_t t1 = ggml_time_ms();
    int32_t ret = mtmd_encode_chunk(context_->ctx_vision.get(), chunk.get());
    LOG_INF("image encode in %" PRId64 " ms\n", ggml_time_ms() - t1);
    if (ret != 0) {
        LOG_ERR("failed to encode image\n");
        return;
    }

    auto embd = mtmd_get_output_embd(context_->ctx_vision.get());
    size_t n_embd = mtmd_input_chunk_get_n_tokens(chunk.get()) * llama_model_n_embd(context_->model);
    if (embd && n_embd > 0) {
        std::vector<float> embeddings(embd, embd + n_embd);
        encode_cache_->store(chunk.get(), embeddings);
    }
}

void EncoderSheduler::process_encoder() {
    while (true) {
        std::function<void()> task = nullptr;
        {
            std::unique_lock<std::mutex> lock(encoder_queue_mutex_);
            encode_condition_.wait(lock, [this] { return !encoder_queue_.empty() || stop_flag_.load(); });
            if (stop_flag_.load()) break;

            task = std::move(encoder_queue_.front());
            encoder_queue_.pop();
        }

        if (task == nullptr) continue;  // Skip if task is null

        try {
            task();
        } catch (const std::exception& e) {
            LOG_ERR("failed to image encode\n");
        }
    }
}