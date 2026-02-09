/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Flex, message, Modal, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { Sender } from '@ant-design/x';
import { Icon, RuleForm } from '@/components';
import { classNames } from '@/utils/util';
import { useRuleFormUpdates } from '@/hooks/useRuleFormUpdates';
import { useChatStore } from '@/stores/chatStore';
import { useGlobalSocket } from '@/hooks/useGlobalSocket';
import { SelectedItemsPrefix, BottomControlButtons } from './components';
import styles from './style.module.less';

/**
 * Send Component - Message input component with rule creation functionality
 * 发送组件 - 带有规则创建功能的消息输入组件
 *
 * @param {Object} props - Component props
 * @param {Function} props.openTimeoutGoToBottom - Function to start auto-scroll timeout
 * @param {Function} props.clearTimeoutGoToBottom - Function to clear auto-scroll timeout
 * @returns {JSX.Element} Send component
 */
const Send = ({
  openTimeoutGoToBottom,
  clearTimeoutGoToBottom,
}) => {
  const { t } = useTranslation();

  const {
    input,
    isAnswering,
    currentAnswer,
    answerMessages,
    isSocketActive,
    setInput,
    setIsAnswering,
    setCurrentAnswer,
    globalSendMessage
  } = useChatStore();

  // const [createModalVisible, setCreateModalVisible] = useState(false);
  // const { loading, handleSaveRule } = useRuleFormUpdates();

  const socketActions = useGlobalSocket();

  useEffect(() => {
    console.log('Send component: clear scroll related timers', { isSocketActive, clearTimeoutGoToBottom });
    if (!isSocketActive && clearTimeoutGoToBottom) {
      clearTimeoutGoToBottom();
    }
  }, [isSocketActive, clearTimeoutGoToBottom]);


  const handleSend = useCallback(async (text = '', defaultMcpList = []) => {
    // use global send message method, handle all common logic
    const messageData = await globalSendMessage(
      text,
      defaultMcpList.length > 0 ? defaultMcpList : null,
      {
        onBeforeSend: () => {
          console.log('Send component: about to send message:', { text, defaultMcpList });
        }
      }
    );

    if (!messageData) {return;}

    try {
      // use global Socket to send message
      const requestId = socketActions.sendMessage(messageData);

      console.log('Socket message send success, request ID:', requestId);

      openTimeoutGoToBottom && openTimeoutGoToBottom();

    } catch (error) {
      console.error('Socket send failed:', error);
      message.error(t('instant.chat.sendMessageFailed'));
      setIsAnswering(false);
    }
  }, [globalSendMessage, socketActions, openTimeoutGoToBottom, setIsAnswering]);


  useEffect(() => {
    if (currentAnswer) {
      setCurrentAnswer(prev => ({
        ...prev,
        socketMessages: answerMessages
      }));
    }
  }, [answerMessages]);

  // stop message processing
  const closeMessage = useCallback(() => {
    socketActions.globalCloseMessage();
  }, [socketActions]);

  return (
    <>
      <div className={styles.sendWrap}>
        <Sender
          value={input}
          onChange={setInput}
          autoSize={{ minRows: 3, maxRows: 6 }}
          placeholder={t('instant.chat.inputPlaceholder')}
          onSubmit={handleSend}
          loading={isAnswering}
          disabled={false}
          prefix={<SelectedItemsPrefix />}
          footer={({ components }) => {
            const { SendButton, LoadingButton } = components;
            return (
              <Flex align="center" gap={0}>

                <BottomControlButtons
                  // onCreateRuleClick={() => setCreateModalVisible(true)}
                />

                <Flex align="center" style={{ flex: 1, justifyContent: 'flex-end' }}>
                  {isAnswering ? (
                    <LoadingButton onClick={() => {
                      closeMessage();
                    }} />
                  ) : (
                    <SendButton
                      type="primary"
                      disabled={isAnswering || !input.trim()}
                      className={styles.sendBtn}
                      icon={<Icon
                        color={(isAnswering || !input.trim()) ? 'var(--text-color-send-text-disabled)' : 'var(--text-color-send-text)'}
                        name="instantFooterSend"
                        size={15} />
                      }
                    >
                      <span className={classNames(styles.sendBtnText, (isAnswering || !input.trim()) ? styles.disabled : '')}>
                        {t('common.send')}
                      </span>
                    </SendButton>
                  )}
                </Flex>
              </Flex>
            );
          }}
          actions={false}
        />
      </div>

      {/* <Modal
        title={t('smartCenter.createRule')}
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={null}
        destroyOnClose
        centered
      >
        <RuleForm
          mode="create"
          onSubmit={async (formData) => {
            await handleSaveRule(formData);
            setCreateModalVisible(false);
          }}
          loading={loading}
        />
      </Modal> */}
    </>
  );
}

export default Send;
