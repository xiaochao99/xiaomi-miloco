/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';

/**
 * ExceptionMessage Component - Exception message component
 * 异常消息组件
 *
 * @param {Object} data - The data to display
 * @returns {JSX.Element} Exception message component
 */
const ExceptionMessage = ({ data }) => {
  const { message } = data;
  return (
    <div style={{
      color: '#dc3545',
      fontSize: '12px',
      padding: '8px 12px',
      backgroundColor: '#fff5f5',
      border: '1px solid #feb2b2',
      borderRadius: '6px',
      margin: '4px 0'
    }}>
      {message}
    </div>
  );
};

export default ExceptionMessage;
