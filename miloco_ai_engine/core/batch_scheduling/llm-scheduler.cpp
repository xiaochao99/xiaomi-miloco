/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "llm-scheduler.h"

LlmScheduler::LlmScheduler(LlamaMicoContext* context) : context_(context) {
    memory_scheduler_ = static_cast<LlamaMemoryScheduler*>(context->memory_scheduler);
}

LlmScheduler::~LlmScheduler() {}

void LlmScheduler::block_waitting_seq(llama_seq_id seq_id) {
    std::unique_lock<std::mutex> lock(seq_set_mutex_);
    finish_condition_.wait(lock, [this, seq_id]() { return running_seq_[seq_id] <= 0; });
}

void LlmScheduler::submit_embedding_infer(std::shared_ptr<mtmd_input_chunk> chunk,
                                          std::shared_ptr<std::vector<float>>& embeddig, llama_seq_id seq_id) {
    {
        std::unique_lock<std::mutex> lock(seq_set_mutex_);
        running_seq_[seq_id]++;
    }

    std::function<void()> task = [this, chunk, embeddig, seq_id]() {
        llama_pos past = this->context_->get_seq_state(seq_id).n_past.load(), new_past;

        int ret = mtmd_helper_decode_image_chunk(context_->ctx_vision.get(), context_->lctx, chunk.get(),
                                                 embeddig->data(), past, seq_id, context_->n_batch, &new_past);

        this->context_->get_seq_state(seq_id).n_past.store(new_past);
        if (ret != 0) {
            LOG_ERR("image infer: failed to decode image\n");
            this->context_->get_seq_state(seq_id).last_token.store(-1);
        } else
            this->context_->get_seq_state(seq_id).last_token.store(0);  // TODO: get last token

        std::unique_lock<std::mutex> lock(this->seq_set_mutex_);
        if (this->running_seq_[seq_id] > 0) --this->running_seq_[seq_id];

        this->finish_condition_.notify_all();
    };

    memory_scheduler_->submit_function_use_mem(task);
}

void LlmScheduler::submit_token_infer(llama_batch text_batch) {
    {
        std::unique_lock<std::mutex> lock(seq_set_mutex_);
        for (int i = 0; i < text_batch.n_tokens; i++) {
            running_seq_[text_batch.seq_id[i][0]]++;  // NOTE: only one seq_id in each token
        }
    }

    std::function<void()> task = [this, text_batch]() {
        int64_t t1 = ggml_time_ms();
        if (llama_decode(context_->lctx, text_batch)) {
            LOG_ERR("text infer: failed to decode token\n");
            for (int32_t i = 0; i < text_batch.n_tokens; i++)
                context_->get_seq_state(text_batch.seq_id[i][0]).last_token.store(-1);
        } else {
            for (int32_t i = 0; i < text_batch.n_tokens; i++) {
                if (text_batch.logits[i]) {
                    llama_token token_id = common_sampler_sample(context_->smpl, context_->lctx, i);
                    common_sampler_accept(context_->smpl, token_id, true);

                    for (int32_t j = 0; j < text_batch.n_seq_id[i]; ++j)
                        context_->get_seq_state(text_batch.seq_id[i][j]).last_token.store(token_id);
                } else {
                    // NOTE: only one seq_id in each token
                    context_->get_seq_state(text_batch.seq_id[i][0]).last_token.store(0);
                }
            }
        }
        LOG_DBG("text decode in %" PRId64 " ms, count %d token\n", ggml_time_ms() - t1, text_batch.n_tokens);
        // Uniformly delete seq_id
        std::unique_lock<std::mutex> lock(this->seq_set_mutex_);
        for (int32_t i = 0; i < text_batch.n_tokens; i++) {
            if (this->running_seq_[text_batch.seq_id[i][0]] > 0) --this->running_seq_[text_batch.seq_id[i][0]];

            this->finish_condition_.notify_all();
        }
    };

    memory_scheduler_->submit_function_use_mem(task);
}