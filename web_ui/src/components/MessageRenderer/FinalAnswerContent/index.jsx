/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';

/**
 * FinalAnswerContent Component - Final answer content component
 * 最终答案内容组件
 *
 * @param {Object} content - The content to display
 * @returns {JSX.Element} Final answer content component
 */
const FinalAnswerContent = ({ content }) => {
  return (
    <div style={{
      fontSize: '14px',
      color: 'var(--text-color)',
      fontWeight: '500',
      lineHeight: '1.8',
      margin: '15px 0px 0px',
    }}>
      <ReactMarkdown
        components={{
          p: ({children}) => <p style={{ margin: 0}}>{children}</p>
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default FinalAnswerContent;
