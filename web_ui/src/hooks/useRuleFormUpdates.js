/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { deleteSmartRuleV2, getSmartRulesV2, saveSmartRuleV2, updateSmartRuleV2 } from "@/api";
import { message } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export const useRuleFormUpdates = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [rules, setRules] = useState([]);

  const fetchRules = async () => {
    try {
      const ruleList = await getSmartRulesV2();
      const normalized = (ruleList?.data || []).map(rule => ({
        id: rule.id,
        name: rule.name,
        enabled: rule.enabled,
        condition_type: rule.trigger?.type || 'llm',
        condition: rule.trigger?.llm_condition || rule.trigger?.camera_condition || rule.trigger?.ha_condition || '',
        ha_condition: rule.trigger?.ha_condition || '',
        trigger_entity_id: rule.targets?.trigger_entity_id || null,
        detection_condition: rule.trigger?.detection_condition || null,
        cameras: rule.targets?.camera_ids || [],
        ha_devices: rule.targets?.ha_device_ids || [],
        execute_info: rule.execute_info || {},
        filter: rule.filter || null,
        __raw_v2: rule,
      }));
      setRules(normalized);
    } catch (error) {
      console.error('fetchRules error', error);
      message.error(t('smartCenter.getRuleListFailed'));
    }
  };

  const buildRuleData = (formData) => {
    const camera_dids = Array.isArray(formData.cameras)
      ? formData.cameras.map(camera => typeof camera === 'object' ? camera.did : camera)
      : formData.cameras || [];
    const conditionType = formData.condition_type || 'llm';
    const ruleData = {
      name: formData.name,
      enabled: formData.enabled !== undefined ? formData.enabled : true,
      trigger: {
        type: conditionType,
        llm_condition: conditionType === 'llm' || conditionType === 'detection' || conditionType === 'face_recognition'
          ? (formData.condition || '')
          : null,
        camera_condition: conditionType === 'hybrid' ? (formData.condition || '') : null,
        ha_condition: conditionType === 'direct' || conditionType === 'hybrid'
          ? (formData.ha_condition || formData.condition || '')
          : null,
        detection_condition: formData.detection_condition || null,
      },
      targets: {
        camera_ids: camera_dids || [],
        ha_device_ids: Array.isArray(formData.ha_devices) ? formData.ha_devices : [],
        trigger_entity_id: formData.trigger_entity_id || null,
      },
      execute_info: formData.execute_info || {
        ai_recommend_execute_type: formData.ai_recommend_execute_type || 'dynamic',
        ai_recommend_action_descriptions: formData.ai_recommend_action_descriptions || [],
        ai_recommend_actions: formData.ai_recommend_actions || [],
        automation_actions: formData.automation_actions || [],
        mcp_list: formData.mcp_list || [],
        notify: formData.notify || null,
      },
      filter: formData.filter || null,
    };

    return ruleData;
  };

  const handleSaveRule = async (formData) => {
    try {
      setLoading(true);
      // formData from RuleForm is already in v2 format (via convertFormDataToBackend).
      // Pass directly to API without re-processing through buildRuleData.
      console.log('[handleSaveRule] Sending v2 create:', JSON.stringify(formData, null, 2));
      const response = await saveSmartRuleV2(formData);

      if (response?.code === 0) {
        message.success(t('smartCenter.ruleSaved'));
        await fetchRules();
        return true
      } else {
        message.error(response?.message || t('smartCenter.operationFailed'));
        return false;
      }
    } catch (error) {
      console.error('handleSaveRule error', error);
      message.error(t('smartCenter.operationFailed'));
      return false;
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateRule = async (rule, formData) => {
    try {
      setLoading(true);
      // formData from RuleForm is already in v2 format (via convertFormDataToBackend).
      // Do NOT pass through buildRuleData which expects flat form format —
      // doing so would destroy the nested trigger/targets structure.
      const ruleData = {
        ...formData,
        id: rule.id,
        // Ensure enabled comes from the current rule state, not stale form data
        enabled: rule.enabled !== undefined ? rule.enabled : (formData.enabled ?? true),
      };

      console.log('[handleUpdateRule] Sending v2 update:', JSON.stringify(ruleData, null, 2));

      const response = await updateSmartRuleV2(rule.id, ruleData);

      if (response && response.code === 0) {
        message.success(t('smartCenter.ruleUpdated'));
        await fetchRules();
      } else {
        message.error(response?.message || t('smartCenter.updateFailed'));
      }
    } catch (error) {
      console.error('updateRule error', error);
      message.error(t('smartCenter.updateFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRule = async (rule) => {
    try {
      const response = await deleteSmartRuleV2(rule.id);
      if (response?.code === 0) {
        message.success(t('smartCenter.ruleDeleted'));
        await fetchRules();
      } else {
        message.error(response?.message || t('smartCenter.deleteFailed'));
      }
    } catch (error) {
      console.error('deleteRule error', error);
      message.error(t('smartCenter.deleteFailed'));
    }
  };

  const handleToggleRule = async (rule, checked) => {
    try {
      // ── Build camera IDs array ──
      const camera_dids = (rule.cameras)
        ? (Array.isArray(rule.cameras)
            ? rule.cameras.map(camera => typeof camera === 'object' ? camera.did : camera)
            : [rule.cameras])
        : [];

      // ── Build HA device IDs array ──
      const ha_device_dids = (rule.ha_devices)
        ? (Array.isArray(rule.ha_devices)
            ? rule.ha_devices.map(device => typeof device === 'object' ? device.did : device)
            : [rule.ha_devices])
        : [];

      // ── Extract MCP client IDs, filtering out invalid entries ──
      const rawMcpList = rule.execute_info?.mcp_list || [];
      const mcpClientIds = rawMcpList
        .map(mcp => {
          if (typeof mcp === 'string') return mcp;
          return mcp?.client_id;
        })
        .filter(id => id && typeof id === 'string');

      // ── Build clean v2 format update data directly (no spread of full rule object) ──
      const conditionType = rule.condition_type || 'llm';
      const updateData = {
        name: rule.name,
        enabled: checked,
        trigger: {
          type: conditionType,
          llm_condition: (conditionType === 'llm' || conditionType === 'detection' || conditionType === 'face_recognition')
            ? (rule.condition || null)
            : null,
          camera_condition: conditionType === 'hybrid' ? (rule.condition || null) : null,
          ha_condition: (conditionType === 'direct' || conditionType === 'hybrid')
            ? (rule.ha_condition || null)
            : null,
          detection_condition: rule.detection_condition || null,
        },
        targets: {
          camera_ids: camera_dids,
          ha_device_ids: ha_device_dids,
          trigger_entity_id: rule.trigger_entity_id || null,
        },
        execute_info: {
          ai_recommend_execute_type: rule.execute_info?.ai_recommend_execute_type || 'static',
          ai_recommend_action_descriptions: rule.execute_info?.ai_recommend_action_descriptions || [],
          ai_recommend_actions: rule.execute_info?.ai_recommend_actions || [],
          automation_actions: rule.execute_info?.automation_actions || [],
          mcp_list: mcpClientIds,
          notify: rule.execute_info?.notify || null,
          xiaoai_broadcast: rule.execute_info?.xiaoai_broadcast || null,
          xiaoai_wakeup: rule.execute_info?.xiaoai_wakeup || null,
          target_entities: rule.execute_info?.target_entities || null,
        },
        filter: rule.filter || null,
      };

      console.log('[handleToggleRule] Sending v2 update:', JSON.stringify(updateData, null, 2));

      const response = await updateSmartRuleV2(rule.id, updateData);
      if (response.code === 0) {
        fetchRules();
      } else {
        message.error(response?.message || t('smartCenter.statusUpdateFailed'));
      }
    } catch (error) {
      console.error('handleToggleRule error', error);
      message.error(t('smartCenter.statusUpdateFailed'));
    }
  };

  return {
    loading,
    rules,
    pageLoading,
    setPageLoading,
    fetchRules,
    buildRuleData,
    handleSaveRule,
    handleUpdateRule,
    handleDeleteRule,
    handleToggleRule,
  };
};
