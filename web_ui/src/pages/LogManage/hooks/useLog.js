/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useEffect } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { getRuleTriggerLogs, getSmartRules } from '@/api';

/**
 * useLog Hook - log management related business logic
 * contains data fetching, parsing, image processing
 *
 * @returns {Object} contains state and methods
 */
const useLog = () => {
  const { t } = useTranslation();
  const [recordData, setRecordData] = useState([]);
  const [totalItems, setTotalItems] = useState(0);
  const [rulesLength, setRulesLength] = useState(0);
  const [imageModalVisible, setImageModalVisible] = useState(false);
  const [currentImageData, setCurrentImageData] = useState([]);
  const [loading, setLoading] = useState(true);

  /**
   * parse rule trigger logs data
   * @param {Array} data - original data
   * @returns {Array} parsed data
   */
  const parseDataFun = (data) => {
    const res = [];

    if (!Array.isArray(data)) {
      console.warn('parseDataFun: data is not an array', data);
      return [];
    }

    (data || []).forEach(item => {
      if (!item) { return; }
      const {
        timestamp,
        trigger_rule_name,
        trigger_rule_condition,
        condition_results = [],
        execute_result = null
      } = item;

      const safeExecuteResult = execute_result || {};

      const cameraResults = (condition_results || []).map(condition => {
        const { camera_info = {}, channel, result, images = [] } = condition;
        return {
          camera_info,
          channel,
          result,
          images
        };
      });

      const {
        ai_recommend_execute_type = 'static',
        ai_recommend_action_execute_results = [],
        automation_action_execute_results = [],
        ai_recommend_dynamic_execute_result = null,
        notify_result = null
      } = safeExecuteResult;

      const parseActionResult = (actionResult) => {
        const { action = {}, result = false } = actionResult || {};
        const {
          mcp_client_id = '',
          mcp_tool_name = '',
          mcp_server_name = '',
          introduction = ''
        } = action || {};

        let resultText = '';

        if (mcp_server_name && introduction) {
          resultText = introduction;
        } else if (mcp_server_name && mcp_tool_name) {
          resultText = `${mcp_server_name} - ${mcp_tool_name}`;
        } else if (mcp_client_id && mcp_tool_name) {
          resultText = `${mcp_client_id} - ${mcp_tool_name}`;
        }

        return {
          text: resultText,
          success: result
        };
      };

      let executionResults = [];
      let isDynamic = false;
      let dynamicExecuteResult = null;

      if (ai_recommend_execute_type === 'static') {
        const automationResults = (automation_action_execute_results || [])
          .map(parseActionResult)
          .filter(item => item.text);
        const aiRecommendResults = (ai_recommend_action_execute_results || [])
          .map(parseActionResult)
          .filter(item => item.text);
        executionResults = [...automationResults, ...aiRecommendResults];
      } else if (ai_recommend_execute_type === 'dynamic') {
        isDynamic = true;
        dynamicExecuteResult = ai_recommend_dynamic_execute_result;
        const automationResults = (automation_action_execute_results || [])
          .map(parseActionResult)
          .filter(item => item.text);
        executionResults = [...automationResults];
      }

      let notifyResult = null;
      if (notify_result && notify_result.notify) {
        const { notify = {}, result = false } = notify_result;
        const { content = '' } = notify;
        if (content) {
          notifyResult = {
            text: content,
            success: result,
            isNotification: true
          };
        }
      }

      const aiRecommendActionDescriptions = ai_recommend_dynamic_execute_result?.ai_recommend_action_descriptions || [];

      const date = new Date(timestamp);
      const dateStr = date.toLocaleDateString();
      const timeStr = date.toLocaleTimeString();
      const time = `${dateStr}\n${timeStr}`;
      res.push({
        time: time,
        rule: trigger_rule_name,
        triggerCondition: trigger_rule_condition,
        executionResults,
        notifyResult,
        cameraResults,
        executeType: ai_recommend_execute_type,
        isDynamic,
        dynamicExecuteResult,
        aiRecommendActionDescriptions,
        rawData: item
      });
    });
    return res;
  };

  /**
   * fetch rule trigger logs list
   */
  const fetchRuleTriggerList = async () => {
    try {
      const response = await getRuleTriggerLogs();
      if (response?.code === 0) {
        const { rule_logs = [], total_items = 0 } = response?.data || {};
        const parseData = parseDataFun(rule_logs || []);
        setRecordData(parseData);
        setTotalItems(total_items);
      } else {
        message.error(response?.message || t('logManage.fetchRuleTriggerListFailed'));
      }
    } catch (error) {
      console.error('fetchRuleTriggerList failed:', error);
    }
  };

  /**
   * fetch smart rules list
   */
  const fetchRules = async () => {
    try {
      const ruleList = await getSmartRules();
      const { data: ruleListData = [] } = ruleList || {};
      const activeRules = ruleListData.filter(rule => rule.enabled).length;
      setRulesLength(activeRules);
    } catch (error) {
      console.error('fetchRules failed:', error);
    }
  };

  /**
   * handle image click event
   * @param {Array} data - image data
   */
  const handleImageClick = (data) => {
    setCurrentImageData(data);
    setImageModalVisible(true);
  };

  /**
   * handle close image modal
   */
  const handleCloseImageModal = () => {
    setImageModalVisible(false);
    setCurrentImageData([]);
  };

  const initData = async () => {
    setLoading(true);
    await fetchRuleTriggerList();
    await fetchRules();
    setLoading(false);
  };

  useEffect(() => {
    initData();
  }, []);

  return {
    // data
    recordData,
    totalItems,
    rulesLength,
    imageModalVisible,
    currentImageData,
    loading,

    // methods
    fetchRuleTriggerList,
    fetchRules,
    handleImageClick,
    handleCloseImageModal,
    initData
  };
};

export default useLog;
