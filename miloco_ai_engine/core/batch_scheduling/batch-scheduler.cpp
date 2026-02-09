/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "batch-scheduler.h"

BatchScheduler::BatchScheduler(LlamaMicoContext* context, size_t batch_time_wait)
    : context_(context), time_wait_(batch_time_wait) {
    encoder_scheduler_ = std::make_unique<EncoderSheduler>(context);
    llm_scheduler_ = std::make_unique<LlmScheduler>(context);

    if (context->kv_cache_seq > 0) {
        kv_cache_ = std::make_unique<ChunkInferCache>((size_t)context->kv_cache_seq, context);
    }

    scheduler_thread_ = new std::thread(&BatchScheduler::process_batch, this);

    context->batch_scheduler = (void*)this;
}

BatchScheduler::~BatchScheduler() {
    stop_flag_.store(true);
    task_condition_.notify_one();
    if (scheduler_thread_) {
        scheduler_thread_->join();
        delete scheduler_thread_;
    }
}

void BatchScheduler::blocking_infer(std::shared_ptr<mtmd::input_chunks> input_chunks, size_t chat_cmpl_id,
                                    int32_t priority) {
    auto input = std::make_shared<BatchSchedulerInput>(input_chunks, chat_cmpl_id, priority);
    for (const auto& chunk : input->input_chunks) {  // encoder
        auto chunk_type = mtmd_input_chunk_get_type(chunk->input_chunk.get());
        if (chunk_type != MTMD_INPUT_CHUNK_TYPE_IMAGE) continue;
        encoder_scheduler_->submit_encoder_task(chunk->input_chunk);
    }

    auto hashs = chunk_hashs(input_chunks.get());

    auto& state = context_->get_seq_state(chat_cmpl_id);
    for (size_t i = 0; i < input_chunks->size(); i++) {
        auto chunk = input->input_chunks[i];
        std::string chunk_hash = hashs[i];

        if (kv_cache_ && i != input_chunks->size() - 1) {  // NOTE: only cache image infer chunks now
            // wait for kv cache, if not ready, wait
            kv_cache_->block_waiting_and_prepare(chunk_hash);
            if (kv_cache_->storing(chunk_hash)) {  // Internal inference storage
                auto entry = kv_cache_->lookup(chunk_hash);
                bool success = kv_cache_->apply_cache_entry(entry, chunk->cmpl_id);
                if (success) {
                    chunk->status = TaskStatus::COMPLETED;
                    state.last_token.store(entry->last_token);
                    state.n_past.store(entry->pos_end);
                    continue;
                }
            }
        }

        // wait for encoder
        if (mtmd_input_chunk_get_type(chunk->input_chunk.get()) == MTMD_INPUT_CHUNK_TYPE_IMAGE) {
            chunk->embeddig = encoder_scheduler_->wait_for_result(chunk->input_chunk);
            if (!chunk->embeddig) {
                LOG_ERR("Encoder embedding failed\n");
                chunk->status = TaskStatus::FAILED;
                state.last_token.store(-1);
                if (kv_cache_) kv_cache_->unprepared(chunk_hash);
                break;
            }
        }

        {  // Start inference
            std::unique_lock<std::mutex> task_lock(task_queue_mutex_);
            task_queue_.push(chunk);
            task_condition_.notify_one();
            finish_condition_.wait(task_lock, [this, &chunk]() {
                return chunk->status.load() != TaskStatus::WAIT && chunk->status.load() != TaskStatus::PENDING;
            });
        }

        // wait for llm
        llm_scheduler_->block_waitting_seq(chunk->cmpl_id);

        size_t last_token = state.last_token.load();
        size_t npast = state.n_past.load();

        if (last_token < 0) {
            chunk->status = TaskStatus::FAILED;
            if (kv_cache_) kv_cache_->unprepared(chunk_hash);
            break;
        } else {
            chunk->status = TaskStatus::COMPLETED;
            // NOTE: only cache image infer chunks now
            if (kv_cache_ && i != input_chunks->size() - 1)
                kv_cache_->store(hashs, i, chunk->cmpl_id, last_token, npast);
        }
    }
}

void BatchScheduler::process_batch() {
    std::vector<std::shared_ptr<SycChunkTask>> text_buffer;
    std::vector<std::shared_ptr<SycChunkTask>> image_buffer;
    auto last_text = ggml_time_ms();
    auto last_image = ggml_time_ms();
    size_t text_size = 0, image_size = 0;
    int32_t remaining_wait = time_wait_;

    while (!stop_flag_.load()) {  // event
        std::unique_lock<std::mutex> task_lock(task_queue_mutex_);
        if (text_buffer.empty() && image_buffer.empty()) {
            task_condition_.wait(task_lock, [this]() { return !task_queue_.empty() || stop_flag_.load(); });
        } else {
            auto now = ggml_time_ms();
            int32_t past_time = 0;
            if (!text_buffer.empty()) past_time = std::max(past_time, (int32_t)(now - last_text));
            if (!image_buffer.empty()) past_time = std::max(past_time, (int32_t)(now - last_image));

            remaining_wait = std::max((int32_t)time_wait_ - past_time, 0);
            task_condition_.wait_for(task_lock, std::chrono::milliseconds(remaining_wait),
                                     [this]() { return !task_queue_.empty() || stop_flag_.load(); });
        }
        if (stop_flag_.load()) break;

        if (!task_queue_.empty()) {  // Prepare data
            auto chunk = std::move(task_queue_.top());
            task_queue_.pop();
            switch (mtmd_input_chunk_get_type(chunk->input_chunk.get())) {
                case MTMD_INPUT_CHUNK_TYPE_TEXT:
                    if (text_buffer.empty()) last_text = ggml_time_ms();
                    text_buffer.push_back(chunk);
                    text_size += mtmd_input_chunk_get_n_tokens(chunk->input_chunk.get());
                    break;
                case MTMD_INPUT_CHUNK_TYPE_IMAGE:
                    if (image_buffer.empty()) last_image = ggml_time_ms();
                    image_buffer.push_back(chunk);
                    image_size += mtmd_input_chunk_get_n_tokens(chunk->input_chunk.get());
                    break;
                default:
                    // do nothing
                    break;
            }
        }

        {  // Prepared text batch
            auto now = ggml_time_ms();
            bool text_infer = false;
            if (!text_buffer.empty()) text_infer |= (now - last_text) >= time_wait_;
            text_infer |= text_size >= text_batch_size_;
            if (text_infer) {
                process_text_batch(text_buffer);  // Submit to LlmScheduler
                text_buffer.clear();
                last_text = ggml_time_ms();
                text_size = 0;
            }
        }
        {  // Prepared image batch
            auto now = ggml_time_ms();
            bool image_infer = false;
            if (!image_buffer.empty()) image_infer |= (now - last_image) >= time_wait_;
            image_infer |= image_size >= image_batch_size_;
            if (image_infer) {
                process_image_batch(image_buffer);  // Submit to LlmScheduler
                image_buffer.clear();
                last_image = ggml_time_ms();
                image_size = 0;
            }
        }
    }
}

void BatchScheduler::process_text_batch(std::vector<std::shared_ptr<SycChunkTask>> text_buffer) {
    llama_batch text_batch = llama_batch_init(context_->n_batch, 0, 1);
    int32_t last_uncomplie = 0;  // Splice batch
    for (int32_t i = 0; i < text_buffer.size(); i++) {
        auto chunk = text_buffer[i];
        size_t n_tokens;
        const auto tokens = mtmd_input_chunk_get_tokens_text(chunk->input_chunk.get(), &n_tokens);
        size_t seq_id = chunk->cmpl_id;
        auto& state = context_->get_seq_state(seq_id);

        size_t token_index = 0;
        while (token_index < n_tokens) {  // Single chunk truncated
            for (; token_index < n_tokens && text_batch.n_tokens < context_->n_batch; token_index++) {  // Build batch
                std::vector<llama_seq_id> seqs;
                seqs.push_back(seq_id);
                common_batch_add(text_batch, tokens[token_index], state.n_past.fetch_add(1), seqs, false);
            }
            if (token_index == n_tokens && chunk->is_last_chunk) text_batch.logits[text_batch.n_tokens - 1] = true;
            if (text_batch.n_tokens == context_->n_batch) {  // Batch is full
                llm_scheduler_->submit_token_infer(text_batch);
                int32_t last = ((token_index == n_tokens) ? i : i - 1);  // Whether this chunk is completed
                for (int t = last_uncomplie; t <= last; t++) text_buffer[t]->status.store(TaskStatus::IN_PROGRESS);
                text_batch = llama_batch_init(context_->n_batch, 0, 1);
                last_uncomplie = last + 1;
            }
        }
    }
    if (text_batch.n_tokens > 0) {
        llm_scheduler_->submit_token_infer(text_batch);
        for (int t = last_uncomplie; t < text_buffer.size(); t++) text_buffer[t]->status.store(TaskStatus::IN_PROGRESS);
    }
    finish_condition_.notify_all();
}

void BatchScheduler::process_image_batch(std::vector<std::shared_ptr<SycChunkTask>> image_buffer) {
    for (int32_t i = 0; i < image_buffer.size(); i++) {  // NOTE: image not support batch now
        llm_scheduler_->submit_embedding_infer(image_buffer[i]->input_chunk, image_buffer[i]->embeddig,
                                               image_buffer[i]->cmpl_id);
        image_buffer[i]->status.store(TaskStatus::IN_PROGRESS);
    }
    finish_condition_.notify_all();
}