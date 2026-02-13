/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { deleteSmartRule, getSmartRules, saveSmartRule, updateSmartRule } from "@/api";
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
      const ruleList = await getSmartRules();
      setRules(ruleList?.data || []);
    } catch (error) {
      console.error('fetchRules error', error);
      message.error(t('smartCenter.getRuleListFailed'));
    }
  };

  const buildRuleData = (formData) => {
    const camera_dids = Array.isArray(formData.cameras)
      ? formData.cameras.map(camera => typeof camera === 'object' ? camera.did : camera)
      : formData.cameras || [];
    const ruleData = {
      ...formData,
      cameras: camera_dids,
      enabled: formData.enabled !== undefined ? formData.enabled : true,
    };

    return ruleData;
  };

  const handleSaveRule = async (formData) => {
    try {
      setLoading(true);
      const response = await saveSmartRule(formData);

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
      const response = await updateSmartRule(rule.id, ruleData);

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
      const response = await deleteSmartRule(rule.id);
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

      const updateData = {
        name: rule.name,
        cameras: camera_dids,
        ha_devices: ha_device_dids,
        condition: rule.condition,
        condition_type: rule.condition_type || 'llm',
        ha_condition: rule.ha_condition || '',
        detection_condition: rule.detection_condition || null,
        execute_info: {
          ...rest,
          mcp_list: mcp_list?.length > 0 ? mcp_list.map(mcp => mcp.client_id) : [],
        },
        filter: rule.filter || null,
        enabled: checked
      };

      const response = await updateSmartRule(rule.id, updateData);
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
