/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { useLogViewerStore } from '@/stores/logViewerStore';
import MessageRenderer from '@/components/MessageRenderer/MessageRenderer';
import { getMessageIsAiGeneratedActions, getMessageIsFinishChat } from '@/utils/instruction/typeUtils';
import styles from './index.module.less';
import { LoadingIndicator } from '../MessageRenderer';

/**
 * LogViewerModal Component - 全局日志弹窗组件
 * LogViewerModal Component - Global log viewer modal component
 *
 * @returns {JSX.Element} Log viewer modal component
 */
const LogViewerModal = () => {
  const { t } = useTranslation();
  const { open, socketMessages, closeModal, socketStatus } = useLogViewerStore();
  const messagesEndRef = useRef(null);
  const containerRef = useRef(null);
  const [showLoadingIndicator, setShowLoadingIndicator] = useState(false);

  useEffect(() => {
    if (!open) {
      const { socketRef } = useLogViewerStore.getState();
      if (socketRef) {
        try {
          socketRef.close(1000);
        } catch (error) {
          console.error('close socket connection failed:', error);
        }
      }
      useLogViewerStore.setState({ socketRef: null, socketStatus: 'DISCONNECTED' });
    }
  }, [open]);

  useEffect(() => {
    if (containerRef.current && socketMessages.length > 0) {
      setShowLoadingIndicator(true);
      const container = containerRef.current;
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
      const { header } = socketMessages[socketMessages.length - 1];
      const { type, namespace, name } = header;
      if(getMessageIsFinishChat(type, namespace, name) || getMessageIsAiGeneratedActions(type, namespace, name)) {
        setShowLoadingIndicator(false);
      }
    }
  }, [socketMessages]);

  return (
    <Modal
      title={
        <div className={styles.header}>
          <span>{t('logManage.executionLogViewer')}</span>
        </div>
      }
      zIndex={2000}
      open={open}
      onCancel={closeModal}
      footer={null}
      width={800}
      destroyOnClose={false}
      className={styles.modal}
    >
      <div className={styles.container} ref={containerRef}>
        <div className={styles.messages}>
          {socketMessages.length === 0 ? (
            <div className={styles.emptyMessage}>
              <LoadingIndicator showText={false} />
            </div>
          ) : (
            <div className={styles.answerContainer}>
              {socketMessages.map((socketMsg, socketIdx) => {
                const socketKey = socketMsg?.header?.request_id && socketMsg?.header?.timestamp
                  ? `${socketMsg.header.request_id}-${socketMsg.header.timestamp}-${socketIdx}`
                  : `socket-${socketIdx}`;

                return (
                  <MessageRenderer
                    key={socketKey}
                    messageData={socketMsg}
                    allMessages={socketMessages}
                  />
                );
              })}
              {showLoadingIndicator && <div style={{ minHeight: '45px', marginTop: '-20px', marginBottom: '-15px' }}><LoadingIndicator showText={false} /></div>}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>
    </Modal>
  );
};

export default LogViewerModal;
