/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import Icon from '@/components/Icon';
import styles from './index.module.less';

/**
 * ThoughtContent Component - Thought content component
 * 思考内容组件
 *
 * @param {Object} content - The content to display
 * @param {string} status - The status of the content
 * @returns {JSX.Element} Thought content component
 */
const ThoughtContent = ({ content, status = 'reflect' }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const { t } = useTranslation();

  const getStatusConfig = (status) => {
    switch (status) {
      case 'reflect':
        return {
          icon: 'instantChatThinking',
          title: t('instant.chat.thinking'),
          color: 'var(--text-color)',
          bgColor: 'var(--bg-color-container)',
          borderColor: 'var(--border-chat-thought)'
        };
      case 'completed':
        return {
          icon: 'instantChatThinking',
          title: t('instant.chat.completed'),
          color: 'var(--text-color)',
          bgColor: 'var(--bg-color-container)',
          borderColor: 'var(--border-chat-thought)'
        };
      default:
        return {
          icon: 'instantChatThinking',
          title: t('instant.chat.thinking'),
          color: 'var(--text-color)',
          bgColor: 'var(--bg-color-container)',
          borderColor: 'var(--border-chat-thought)'
        };
    }
  };

  const config = getStatusConfig(status);

  return (
    <div className={styles.thoughtContent}>
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className={styles.header}
      >
        <Icon
          name={config.icon}
          size={16}
          color={'var(--text-color)'}
          className={`${styles.icon} ${status === 'reflect' ? styles.rotating : ''}`}
        />
        <span className={styles.title}>
          {config.title}
        </span>
        <div className={`${styles.arrow} ${!isExpanded ? styles.collapsed : ''}`}>
          <Icon name="arrow" size={16} color={'var(--text-color)'} />
        </div>

      </div>

      {isExpanded && (
        <div className={styles.content}>
          <ReactMarkdown
            components={{
              p: ({children}) => <p style={{margin: '0'}}>{children}</p>,
              // ul: ({children}) => <ul style={{margin: '8px 0', paddingLeft: '20px'}}>{children}</ul>,
              // li: ({children}) => <li style={{margin: '4px 0'}}>{children}</li>
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
};

export default ThoughtContent;
