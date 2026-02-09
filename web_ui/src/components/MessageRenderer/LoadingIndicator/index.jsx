/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import styles from './index.module.less';
import { useTranslation } from 'react-i18next';

/**
 * LoadingIndicator Component - Loading indicator for AI response
 * 加载指示器组件 - 用于AI回复的加载状态显示
 *
 * @returns {JSX.Element} Loading indicator component
 */
const LoadingIndicator = ({ showText = true }) => {
  const { t } = useTranslation();
  return (
    <div className={styles.loadingContainer}>
      <div className={styles.loadingRow}>
        {showText && <span className={styles.loadingText}>{t('instant.chat.aiThinking')}</span>}
        <div className={styles.loadingDots}>
          <div className={styles.dot}></div>
          <div className={styles.dot}></div>
          <div className={styles.dot}></div>
        </div>
      </div>
    </div>
  );
};

export default LoadingIndicator;
