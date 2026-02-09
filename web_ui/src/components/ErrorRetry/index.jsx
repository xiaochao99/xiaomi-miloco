/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { Button, Result } from 'antd';
import { memo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ReloadOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import styles from './index.module.less';


/**
 * ErrorRetry Component - Error display with retry functionality
 * 错误重试组件 - 显示错误信息和重试按钮
 *
 * @param {Object} props - Component props
 * @param {string} [props.title='error.authFailed'] - Error title
 * @param {string} [props.message='error.authFailedMessage'] - Error description
 * @param {React.ReactNode} [props.icon] - Custom error icon
 * @param {string} [props.buttonText='common.retry'] - Retry button text
 * @param {boolean} [props.loading=false] - Whether retry button is in loading state
 * @param {Function} props.onRetry - Retry callback function
 * @returns {JSX.Element} Error retry component
 */
const ErrorRetry = ({
  title = 'error.authFailed',
  message = 'error.authFailedMessage',
  icon = <ExclamationCircleOutlined />,
  buttonText = 'common.retry',
  loading = false,
  onRetry,
}) => {
  const { t } = useTranslation();
  const handleRetry = useCallback(() => {
    if (onRetry && typeof onRetry === 'function') {
      onRetry();
    }
  }, [onRetry]);

  return (
    <div className={styles.errorRetry}>
      <Result
        icon={icon}
        title={t(title)}
        subTitle={t(message)}
        extra={[
          <Button
            key="retry"
            type="primary"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={handleRetry}
            className={styles.retryButton}
          >
            {t(buttonText)}
          </Button>
        ]}
      />
    </div>
  );
}
export default ErrorRetry;
