/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { getApi, postApi, putApi, deleteApi } from "@/utils/http";

// auth API
export const getJudgeLogin = () => getApi('/api/auth/register-status');
export const getUserLoginOut = () => getApi('/api/auth/logout');
export const setInitPinCode = (data) => postApi('/api/auth/register', data);
export const getPinLogin = (data) => postApi('/api/auth/login', data);
export const setLanguage = (data) => postApi('/api/auth/language', data);
export const getLanguage = () => getApi('/api/auth/language');

// miot API
export const getUserLoginStatus = () => getApi('/api/miot/login_status');
export const getUserInfo = () => getApi('/api/miot/user_info');
export const getCameraList = () => getApi('/api/miot/camera_list');
export const getDeviceList = () => getApi('/api/miot/device_list');
export const getScenesList = () => getApi('/api/miot/scenes');
export const getRefreshMiotInfo = () => getApi('/api/miot/refresh_miot_info');
export const getMiotSceneActions = () => getApi('/api/miot/miot_scene_actions');
export const sendNotification = (data) => getApi(`/api/miot/send_notify?notify=${data}`);
export const refreshMiotDevices = () => getApi('/api/miot/refresh_miot_devices');
export const refreshMiotScenes = () => getApi('/api/miot/refresh_miot_scenes');
export const refreshMiotCamera = () => getApi('/api/miot/refresh_miot_cameras');
export const getRefreshMiotAllInfo = () => getApi('/api/miot/refresh_miot_all_info');

// trigger API
export const saveSmartRule = (data) => postApi('/api/trigger/rule', data);
export const updateSmartRule = (ruleId, data) => putApi(`/api/trigger/rule/${ruleId}`, data);
export const deleteSmartRule = (id) => deleteApi(`/api/trigger/rule/${id}`);

export const getSmartRules = () => getApi('/api/trigger/rules');
export const saveSmartRuleV2 = (data) => postApi('/api/trigger/v2/rule', data);
export const updateSmartRuleV2 = (ruleId, data) => putApi(`/api/trigger/v2/rule/${ruleId}`, data);
export const deleteSmartRuleV2 = (id) => deleteApi(`/api/trigger/v2/rule/${id}`);
export const getSmartRulesV2 = () => getApi('/api/trigger/v2/rules');
export const executeSceneActions = (data) => postApi('/api/trigger/execute_actions', data);
export const getRuleTriggerLogs = (limit = 500) => getApi(`/api/trigger/logs?limit=${limit}`);

// model API
export const getAllModels = () => getApi('/api/model');
export const createModel = (data) => postApi('/api/model', data);
export const getModelDetail = (modelId) => getApi(`/api/model/${modelId}`);
export const updateModel = (modelId, data) => putApi(`/api/model/${modelId}`, data);
export const deleteModel = (modelId) => deleteApi(`/api/model/${modelId}`);
export const getVendorModels = (data) => postApi('/api/model/get_vendor_models', data);
export const setCurrentModel = (modelId, purpose = '') => getApi(`/api/model/set_current_model?${purpose ? `purpose=${purpose}` : ''}${modelId ? `&model_id=${modelId}` : ''}`);
export const getModelPurposes = () => getApi('/api/model/model_purposes');
export const getCudaInfo = () => getApi('/api/model/get_cuda_info');
export const setModelLoad = (data) => postApi('/api/model/load', data, 60000);
// Home Assistant API
export const setHAAuth = (data) => postApi('/api/ha/set_config', data);
export const getHAAuth = () => getApi('/api/ha/get_config');
export const getHaList = () => getApi('/api/ha/automations');
export const getHaAutomationActions = () => getApi('/api/ha/automation_actions');
export const refreshHaAutomation = () => getApi('/api/ha/refresh_ha_automations');
export const getHADeviceList = () => getApi('/api/ha/devices');
export const getHaDevicesGrouped = () => getApi('/api/ha/devices_grouped');
export const getHAEntityStateOptions = (entityId) =>
  getApi(`/api/ha/entity_state_options?entity_id=${encodeURIComponent(entityId)}`);
export const controlHADevice = (data) => postApi('/api/ha/control', data);

// mcp
export const getMCPService = () => getApi('/api/mcp');
export const setMCPService = (data) => postApi('/api/mcp', data);
export const updateMCPService = (id, data) => putApi(`/api/mcp/${id}`, data);
export const deleteMCPService = (id) => deleteApi(`/api/mcp/${id}`);
export const getMCPStatus = () => getApi('/api/mcp/clients/status');
export const reconnectMCPService = (id) => postApi(`/api/mcp/reconnect/${id}`);

// history API
export const getHistoryList = () => getApi('/api/chat/historys');
export const getHistoryDetail = (id) => getApi(`/api/chat/history/${id}`);
export const deleteChatHistory = (id) => deleteApi(`/api/chat/history/${id}`);

// API Token management
export const getAPITokenList = () => getApi('/api/tokens/list');
export const createAPIToken = (data) => postApi('/api/tokens/create', data);
export const deleteAPIToken = (data) => postApi('/api/tokens/delete', data);

// Camera configuration
export const getCameraConfig = () => getApi('/api/miot/camera_config');
export const setCameraConfig = (data) => postApi('/api/miot/camera_config', data);

// RTSP server configuration
export const getRTSPServerConfig = () => getApi('/api/miot/rtsp_server_config');
export const setRTSPServerConfig = (data) => postApi('/api/miot/rtsp_server_config', data);

// RTSP Camera management
export const getRTSPCameras = () => getApi('/api/miot/rtsp_cameras');
export const createRTSPCamera = (data) => postApi('/api/miot/rtsp_cameras', data);
export const updateRTSPCamera = (did, data) => putApi(`/api/miot/rtsp_cameras/${did}`, data);
export const deleteRTSPCamera = (did) => deleteApi(`/api/miot/rtsp_cameras/${did}`);

// Face library / recognition
export const enrollFace = (data) => postApi('/api/face/library/enroll', data, 60000);
export const listFaceProfiles = () => getApi('/api/face/library/list');
export const deleteFaceProfile = (profileId) => deleteApi(`/api/face/library/${profileId}`);
export const searchFaces = (data) => postApi('/api/face/search', data, 60000);

// Xiaomi Bridge API
export const getXiaomiBridgeDevices = () => getApi('/api/xiaomi-bridge/devices');
export const getXiaomiBridgeDevice = (clientId) => getApi(`/api/xiaomi-bridge/devices/${clientId}`);
export const updateXiaomiBridgeDevice = (clientId, data) => putApi(`/api/xiaomi-bridge/devices/${clientId}`, data);
