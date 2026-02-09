/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { Spin } from 'antd';
import styles from './index.module.less';

/**
 * Loading Component - Loading state display
 * 加载组件 - 显示加载状态
 *
 * @param {Object} props - Component props
 * @param {string} [props.size='small'] - Loading spinner size: 'small' | 'default' | 'large'
 * @returns {JSX.Element} Loading component
 */
const Loading = ({ size = 'small' }) => {

  return (
    <div className={styles.loading}>
      <Spin size={size} />
    </div>
  );
}

export default Loading;
