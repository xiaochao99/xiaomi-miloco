/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Select, Tag, Tooltip } from 'antd';

const SelectTagRender = ({ aiRecommendActions, ...props }) => {
  const { label, value, closable, onClose } = props;
  const onPreventMouseDown = event => {
    event.preventDefault();
    event.stopPropagation();
  }
  const action = aiRecommendActions.find(action => action.introduction === label);
  return (
    <Tooltip title={JSON.stringify(action)}>
      <Tag
        color='rgba(0, 0, 0, 0.5)'
        onMouseDown={onPreventMouseDown}
        closable={closable}
        onClose={onClose}
        style={{ margin: 2 }}
      >
        {label}
      </Tag>
    </Tooltip>

  );
};
export default SelectTagRender;
