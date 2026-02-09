/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "mico-config.h"

#include <fstream>
#include <iostream>

#include "chat.h"
#include "common/log.h"
#include "json-partial.h"

using json = nlohmann::ordered_json;

#ifndef LOG_DEBUG_NAME
#define LOG_DEBUG_NAME "debug"
#endif

/** Configuration example
{
    params.sampling.temp = -1;      // greedily sampler
    params.n_gpu_layers = 50;       // all layers use gpu
    params.total_context_num = 32768;           // context size = (n_seq_max(4 cache)  + 1 for query) * (256(main image)
+ 64(sub image) * 5)
    params.chunk_size = 1024;          // logical batch  (must be >=32 to use BLAS) should >= n_ubatch
    params.n_ubatch = 256;          // physical batch  (must be >=32 to use BLAS) should >= main image(256)
    params.n_seq_max = 35;          // maximum sequence length

    params.cache_seq_num = 8;
    // NOTE 10<8192 20<16384mic
}
*/

bool config_params_parse_json(const char* config_json, common_params& params) {
    if (!config_json) {
        LOG_ERR("ERR: config json is empty\n");
        return false;
    }

    try {
        // Parse JSON string
        json config = json::parse(config_json);
        bool res = true;

        if (config.contains("model")) {
            params.model_alias = config["model_name"].get<std::string>();
        }
        if (config.contains("model_path")) {
            params.model.path = config["model_path"].get<std::string>();
        } else {
            res = false;
            LOG_ERR("ERR: model_path is not set in config\n");
        }
        if (config.contains("mmproj_path")) {
            params.mmproj.path = config["mmproj_path"].get<std::string>();
        }

        // Parse optional configuration parameters
        if (config.contains("n_gpu_layers")) {
            params.n_gpu_layers = config["n_gpu_layers"].get<int32_t>();
        }
        if (config.contains("total_context_num")) {
            params.n_ctx = config["total_context_num"].get<int32_t>();
        }
        if (config.contains("chunk_size")) {
            params.n_batch = config["chunk_size"].get<int32_t>();
            params.n_ubatch = config["chunk_size"].get<int32_t>();
        }

        if (config.contains("n_ubatch")) {
            params.n_ubatch = config["n_ubatch"].get<int32_t>();
        }

        if (config.contains("n_seq_max")) {
            params.n_seq_max = config["n_seq_max"].get<int32_t>();
        }
        if (config.contains("cache_seq_num")) {
            params.cache_seq = config["cache_seq_num"].get<int32_t>();
        }
        if (config.contains("mmproj_use_gpu")) {
            params.mmproj_use_gpu = config["mmproj_use_gpu"].get<bool>();
        }
        if (config.contains("context_per_seq")) {
            params.n_usage_context = config["context_per_seq"].get<int32_t>();
        }

        // Parse sampling parameters
        params.sampling.temp = -1;  // Default greedy sampling
        if (config.contains("temp")) {
            params.sampling.temp = config["temp"].get<float>();
        }
        if (config.contains("top_k")) {
            params.sampling.top_k = config["top_k"].get<int32_t>();
        }
        if (config.contains("top_p")) {
            params.sampling.top_p = config["top_p"].get<float>();
        }
        if (config.contains("seed")) {
            params.sampling.seed = config["seed"].get<uint32_t>();
        }

        if (config.contains("log_file")) {
            std::string log_path = config["log_file"].get<std::string>();
            common_log_set_file(common_log_main(), log_path.c_str());
        }
        if (config.contains("log_level")) {
            std::string log_level = config["log_level"].get<std::string>();
            if (log_level == LOG_DEBUG_NAME) common_log_set_verbosity_thold(LOG_DEFAULT_DEBUG);
        }

        // params.cpuparams.n_threads = 10;
        postprocess_cpu_params(params.cpuparams, nullptr);
        postprocess_cpu_params(params.cpuparams_batch, &params.cpuparams);
        return res;
    } catch (const std::exception& e) {
        LOG_ERR("ERR: Failed to parse config JSON: %s\n", e.what());
        return false;
    }
}