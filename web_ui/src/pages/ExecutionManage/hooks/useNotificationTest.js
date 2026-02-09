/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from 'react-i18next';
import { sendNotification } from '@/api';

export const useNotificationTest = () => {
  const { t } = useTranslation();
  const [notificationText, setNotificationText] = useState('');
  const [notificationLoading, setNotificationLoading] = useState(false);

  // send notification
  const handleSendNotification = useCallback(async (text) => {
    setNotificationLoading(true);
    try {
      const res = await sendNotification(text);

      if (res?.code === 0) {
        message.success(t('executionManage.notificationSentSuccess'));
        setNotificationText('');
      } else {
        message.error(res?.message || t('executionManage.notificationSentFailed'));
      }
    } catch (error) {
      console.error('handleSendNotification error', error);
      message.error(t('executionManage.notificationSentFailed'));
    } finally {
      setNotificationLoading(false);
    }
  }, []);

  return {
    notificationText,
    setNotificationText,
    notificationLoading,
    handleSendNotification
  };
};
