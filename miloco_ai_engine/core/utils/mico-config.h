/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */
#ifndef MICO_CONFIG_H
#define MICO_CONFIG_H

#include "common/common.h"
#include "common/log.h"

/**
 * @brief Parse configuration parameters from JSON string
 * @param config_json Configuration string in JSON format
 * @param params Output parameter, parsed configuration parameters
 * @return true on success, false on failure
 */
bool config_params_parse_json(const char* config_json, common_params& params);

#endif  // MICO_CONFIG_H
