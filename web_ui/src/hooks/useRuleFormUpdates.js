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
      const response = await saveSmartRuleV2(buildRuleData(formData));

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
      const ruleData = buildRuleData({
        ...formData,
        mcp_list: formData?.execute_info.mcp_list || rule.execute_info?.mcp_list || [],
      });

      ruleData.enabled = rule.enabled !== undefined ? rule.enabled : true;
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
      const { mcp_list = [], ...rest } = rule.execute_info || {};

      // Build camera IDs array
      const camera_dids = rule.cameras
        ? Array.isArray(rule.cameras)
          ? rule.cameras.map(camera => typeof camera === 'object' ? camera.did : camera)
          : rule.cameras
        : [];

      // Build HA device IDs array
      const ha_device_dids = rule.ha_devices
        ? Array.isArray(rule.ha_devices)
          ? rule.ha_devices.map(device => typeof device === 'object' ? device.did : device)
          : rule.ha_devices
        : [];

      const updateData = buildRuleData({
        ...rule,
        cameras: camera_dids,
        ha_devices: ha_device_dids,
        execute_info: {
          ...rest,
          mcp_list: mcp_list?.length > 0 ? mcp_list.map(mcp => mcp.client_id) : [],
        },
        enabled: checked,
      });

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
