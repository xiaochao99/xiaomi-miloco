/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import { Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { getMessageIsCallToolResult } from '@/utils/instruction/typeUtils';
import Icon from '@/components/Icon';
import ToolResultContent from './ToolResultContent';

/**
 * ToolCallMessage Component - Tool call message component
 * 工具调用消息组件
 *
 * @param {Object} data - The data to display
 * @param {Array} allMessages - The all messages
 * @returns {JSX.Element} Tool call message component
 */
const ToolCallMessage = ({ data, allMessages = [] }) => {
  const { service_name = '', tool_name, id, tool_params = {} } = data;
  const [showResult, setShowResult] = useState(false);
  const { t } = useTranslation();

  const toolResult = allMessages.find(msg => {
    const { type, namespace, name } = msg.header;
    if (getMessageIsCallToolResult(type, namespace, name)) {
      try {
        const resultData = JSON.parse(msg.payload);
        return resultData.id === id;
      } catch {
        return false;
      }
    }
    return false;
  });

  const { payload = {} } = toolResult || {};

  const hasResult = !!toolResult;
  const isFailed = hasResult && JSON.parse(payload)?.success === false;
  const getStatusConfig = () => {
    if (isFailed) {
      return {
        icon: 'toolCallFail',
        title: t('instant.chat.toolCallFail'),
        color: 'rgba(255, 67, 67, 1)',
        bgColor: 'var(--bg-color-chat-call)',
        borderColor: 'var(--border-chat-thought)'
      };
    } else if (hasResult) {
      return {
        icon: 'toolCallSuccess',
        title: t('instant.chat.toolCallSuccess'),
        color: 'rgba(9, 182, 8, 1)',
        bgColor: 'var(--bg-color-chat-call)',
        borderColor: 'var(--border-chat-thought)'
      };
    } else {
      return {
        icon: 'toolCallLoading',
        title: t('instant.chat.toolCallLoading'),
        color: 'rgba(68, 155, 255, 1)',
        bgColor: 'var(--bg-color-chat-call)',
        borderColor: 'var(--border-chat-thought)'
      };
    }
  };

  const config = getStatusConfig();

  return (
    <div style={{
      border: `1px solid ${config.borderColor}`,
      borderRadius: '8px',
      backgroundColor: config.bgColor,
      overflow: 'hidden',
      padding: '12px 16px',
    }}>
      <div
        onClick={() => hasResult && setShowResult(!showResult)}
        style={{
          cursor: hasResult ? 'pointer' : 'default',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}
      >
        {!hasResult ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '16px',
              width: '16px'
            }}
            className="custom-spin"
          >
            <Spin size="small" />
            <style dangerouslySetInnerHTML={{
              __html: `
                .custom-spin .ant-spin-dot i {
                  background-color: ${config.color} !important;
                }
              `
            }} />
          </div>
        ) : (
          <Icon name={config.icon} size={16} />
        )}
        <span style={{
          fontSize: '14px',
          color: config.color,
          fontWeight: '500',
        }}>
          {config.title}
        </span>
        <span style={{
          fontSize: '12px',
          color: 'var(--text-color-6)',
          opacity: 0.8,
          flex: 1,
          marginLeft: '8px'
        }}>
          {`${service_name} ${tool_name}`}
        </span>
        {hasResult && <div style={{
          transform: !showResult ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }}>
          <Icon name="arrow" size={16} color={'#000'} />
        </div>}
      </div>

      {showResult && (
        <div style={{
          marginTop: '16px',
        }}>
          <div style={{
            marginBottom: '16px',
          }}>
            <ToolResultContent title={t('instant.chat.toolExecutionParams')} data={{ result: tool_params }} />
          </div>

          {hasResult && (
            <ToolResultContent title={t('instant.chat.toolExecutionResult')} data={{ result: payload}} />
          )}
        </div>
      )}

    </div>
  );
};

export default ToolCallMessage;
