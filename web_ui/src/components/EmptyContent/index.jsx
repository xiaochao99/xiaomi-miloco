/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Empty } from 'antd';
import styles from './index.module.less';

/**
 * EmptyContent Component - Empty content component
 * 空内容组件
 *
 * @param {Object} props - Component props
 * @param {string} [props.description='No data'] - Description text
 * @param {string} [props.image=null] - Image source
 * @param {object} [props.imageStyle={ width: 72, height: 72 }] - Image style
 * @returns {JSX.Element} Empty content component
 */
const EmptyContent = ({ description = '', image = null, imageStyle = {}, ...props }) => {
  return (
    <div className={styles.emptyContent}>
      <Empty
        description={description}
        image={image || Empty.PRESENTED_IMAGE_DEFAULT}
        imageStyle={imageStyle}
        {...props}
      />
    </div>
  );
};

export default EmptyContent;
