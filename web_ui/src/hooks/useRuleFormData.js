/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useMemo } from 'react';
import { formDataUtils } from '@/utils/ruleFormUtils';

/**
 * Hook for processing rule form data conversion
 * 处理规则表单数据转换的Hook
 *
 * @param {Object} rule - Rule data from backend
 * @returns {Object} Formatted data for form
 */
export const useRuleFormData = (rule) => {
  return useMemo(() => {
    if (!rule) {
      return {
        name: '',
        cameras: [],
        ha_devices: [],
        condition: '',
        ai_recommend_execute_type: 'static',
        trigger_entity_id: null,
        ai_recommend_action_descriptions: [],
        ai_recommend_actions: [],
        automation_actions: [],
        notify: null,
        xiaoai_broadcast: null,
        xiaoai_wakeup: null,
        filter: null,
        mcp_list: [],
      };
    }

    // Support both V1 and V2 rule formats
    // V1 format: direct fields (condition_type, ha_condition, trigger_entity_id)
    // V2 format: nested in trigger/targets (trigger.type, trigger.ha_condition, targets.trigger_entity_id)
    const isV2 = rule.trigger !== undefined && rule.targets !== undefined;
    
    const formData = {
      name: rule.name || '',
      cameras: isV2 ? (rule.targets?.camera_ids || []) : (rule.cameras || []),
      ha_devices: isV2 ? (rule.targets?.ha_device_ids || []) : (rule.ha_devices || []),
      condition: isV2 ? (rule.trigger?.llm_condition || rule.trigger?.camera_condition || '') : (rule.condition || ''),
      condition_type: isV2 ? (rule.trigger?.type || 'llm') : (rule.condition_type || 'llm'),
      ha_condition: isV2 ? (rule.trigger?.ha_condition || '') : (rule.ha_condition || ''),
      trigger_entity_id: isV2 ? (rule.targets?.trigger_entity_id || null) : (rule.trigger_entity_id || null),
      detection_condition: isV2 ? (rule.trigger?.detection_condition || null) : (rule.detection_condition || null),
      ai_recommend_execute_type: rule.execute_info?.ai_recommend_execute_type || 'static',
      ai_recommend_action_descriptions: rule.execute_info?.ai_recommend_action_descriptions || [],
      ai_recommend_actions: rule.execute_info?.ai_recommend_actions || [],
      automation_actions: rule.execute_info?.automation_actions || [],
      notify: rule.execute_info?.notify || null,
      xiaoai_broadcast: rule.execute_info?.xiaoai_broadcast || null,
      xiaoai_wakeup: rule.execute_info?.xiaoai_wakeup || null,
      filter: rule.filter || null,
      mcp_list: rule.execute_info?.mcp_list || [],
    };

    return formData;
  }, [rule]);
};

/**
 * Convert form data to backend format
 * 将表单数据转换为后端格式
 *
 * @param {Object} formData - Form data
 * @returns {Object} Backend format data
 */
export const convertFormDataToBackend = (formData) => {
  const {
    name,
    cameras,
    ha_devices,
    condition,
    condition_type,
    ha_condition,
    trigger_entity_id,
    detection_condition,
    ai_recommend_execute_type,
    ai_recommend_action_descriptions,
    ai_recommend_actions,
    automation_actions,
    notify,
    xiaoai_broadcast,
    xiaoai_wakeup,
    filter,
    mcp_list,
    enabled,
  } = formData;

  const filterData = filter ? formDataUtils.toSubmitFormat(filter) : null;

  const camera_dids = Array.isArray(cameras)
    ? cameras.map(camera => typeof camera === 'object' ? (camera.did || camera) : camera)
    : [];

  const ha_device_ids = Array.isArray(ha_devices)
    ? ha_devices.map(device => typeof device === 'object' ? (device.did || device) : device)
    : [];

  const mcp_list_ids = mcp_list?.length > 0 ? mcp_list.map(mcp => mcp?.client_id) : [];

  const backendData = {
    name,
    cameras: camera_dids,
    ha_devices: ha_device_ids,
    condition,
    condition_type: condition_type,
    ha_condition: ha_condition || null,
    trigger_entity_id: trigger_entity_id || null,
    detection_condition: detection_condition || null,
    execute_info: {
      ai_recommend_execute_type: ai_recommend_execute_type || 'static',
      ai_recommend_action_descriptions: ai_recommend_action_descriptions || [],
      ai_recommend_actions: ai_recommend_actions || [],
      automation_actions: automation_actions || [],
      mcp_list: mcp_list_ids || [],
      xiaoai_broadcast: xiaoai_broadcast || null,
      xiaoai_wakeup: xiaoai_wakeup || null,
      ...(notify && notify.content ? { notify } : {}),
    },
    filter: filterData,
  };

  if (enabled !== undefined) {
    backendData.enabled = enabled;
  }

  return backendData;
};

/**
 * Convert backend data to form format
 * 将后端数据转换为表单格式
 *
 * @param {Object} backendData - Backend data
 * @returns {Object} Form format data
 */
export const convertBackendToFormData = (backendData) => {
  if (!backendData) {
    return null;
  }

  return {
    name: backendData.name || '',
    cameras: backendData.cameras || [],
    ha_devices: backendData.ha_devices || [],
    condition: backendData.condition || '',
    condition_type: backendData.condition_type || 'llm',
    ha_condition: backendData.ha_condition || '',
    trigger_entity_id: backendData.trigger_entity_id || null,
    detection_condition: backendData.detection_condition || null,
    ai_recommend_execute_type: backendData.execute_info?.ai_recommend_execute_type || 'static',
    ai_recommend_action_descriptions: backendData.execute_info?.ai_recommend_action_descriptions || [],
    ai_recommend_actions: backendData.execute_info?.ai_recommend_actions || [],
    automation_actions: backendData.execute_info?.automation_actions || [],
    notify: backendData.execute_info?.notify || null,
    xiaoai_broadcast: backendData.execute_info?.xiaoai_broadcast || null,
    filter: backendData.filter ? formDataUtils.toFormFormat(backendData.filter) : null,
    mcp_list: backendData.execute_info?.mcp_list || [],
    enabled: backendData.enabled,
  };
};
