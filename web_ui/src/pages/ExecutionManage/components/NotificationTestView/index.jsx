/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { Input, Button, Space, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { SendOutlined } from '@ant-design/icons';
import { Card } from '@/components';
import styles from './index.module.less';

/**
 * NotificationTestView Component - Notification test view component
 * 通知测试视图组件
 *
 * @param {Object} notificationText - The notification text to display
 * @param {function} setNotificationText - The function to set the notification text
 * @param {function} onSendNotification - The function to send the notification
 * @param {boolean} loading - Whether the notification is loading
 * @returns {JSX.Element} Notification test view component
 */
const NotificationTestView = ({
  notificationText,
  setNotificationText,
  onSendNotification,
  loading
}) => {
  const { t } = useTranslation();
  const handleNotificationTest = async () => {
    if (!notificationText.trim()) {
      message.warning(t('executionManage.pleaseEnterNotification'));
      return;
    }
    await onSendNotification(notificationText);
  };

  return (
    <div className={styles.automationList}>
      <Card className={styles.notificationTestCard}>
        <div>
          <h3 className={styles.notificationTitle}>{t('executionManage.notificationTest')}</h3>
          <p className={styles.notificationDescription}>
            {t('executionManage.notificationTestDescription')}
          </p>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              placeholder={t('executionManage.pleaseEnterNotification')}
              value={notificationText}
              onChange={(e) => setNotificationText(e.target.value)}
              onPressEnter={handleNotificationTest}
              disabled={loading}
              className={styles.notificationInput}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleNotificationTest}
              loading={loading}
              disabled={!notificationText.trim()}
              className={styles.notificationButton}
            >
              {t('common.send')}
            </Button>
          </Space.Compact>
        </div>
      </Card>
    </div>
  );
};

export default NotificationTestView;
