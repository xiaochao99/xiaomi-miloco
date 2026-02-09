/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';

/**
 * ToolResultContent Component - Tool result content component
 * 工具结果内容组件
 */
const ToolResultContent = ({ data, title = '' }) => {
  const { result } = data;

  return (
    <div>
      <div style={{
        color: 'var(--text-color-6)',
        fontWeight: 'bold',
        marginBottom: '8px',
        fontSize: '12px'
      }}>
        {title}
      </div>
      <pre style={{
        margin: 0,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontSize: '12px',
        color: 'var(--text-color-6)',
        lineHeight: '1.8',
      }}>
        {result}
      </pre>
    </div>
  );
};

export default ToolResultContent;
