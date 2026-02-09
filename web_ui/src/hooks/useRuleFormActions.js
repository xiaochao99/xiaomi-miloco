/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useMemo } from 'react';

/**
 * Hook for processing automation actions selection
 * 处理自动化动作选择的Hook
 *
 * @param {Array} actionOptions - All available action options
 * @param {Array} selectedActions - Selected actions from rule
 * @returns {Object} Grouped actions and selection state
 */
export const useRuleFormActions = (actionOptions = [], selectedActions = []) => {
  const groupedActions = useMemo(() => {
    const grouped = {};

    actionOptions.forEach(action => {
      const serverName = action.mcp_server_name || 'unknown';
      if (!grouped[serverName]) {
        grouped[serverName] = [];
      }

      grouped[serverName].push({
        ...action,
        key: `${serverName}#${action.introduction}`,
      });
    });

    return grouped;
  }, [actionOptions]);

  const serverNames = useMemo(() => {
    return Object.keys(groupedActions);
  }, [groupedActions]);

  const groupedOptions = useMemo(() => {
    const options = [];

    const sortedServerNames = Object.keys(groupedActions).sort();

    sortedServerNames.forEach(serverName => {
      const actions = groupedActions[serverName];
      if (actions && actions.length > 0) {
        options.push({
          label: serverName,
          options: actions.map(action => ({
            label: action.introduction,
            value: action.key,
          })),
        });
      }
    });

    return options;
  }, [groupedActions]);

  const selectedActionKeys = useMemo(() => {
    if (!selectedActions || selectedActions.length === 0) {
      return [];
    }

    if (selectedActions[0] && typeof selectedActions[0] === 'object') {
      return selectedActions.map(action => {
        const serverName = action.mcp_server_name || 'unknown';
        return `${serverName}#${action.introduction}`;
      });
    }

    return selectedActions;
  }, [selectedActions]);

  const selectedActionObjects = useMemo(() => {
    if (!selectedActionKeys || selectedActionKeys.length === 0) {
      return [];
    }

    return selectedActionKeys
      .map(key => {
        return actionOptions.find(action => {
          const serverName = action.mcp_server_name || 'unknown';
          return `${serverName}#${action.introduction}` === key;
        });
      })
      .filter(Boolean);
  }, [selectedActionKeys, actionOptions]);

  return {
    groupedActions,
    serverNames,
    groupedOptions,
    selectedActionKeys,
    selectedActionObjects,
  };
};

