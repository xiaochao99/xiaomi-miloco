/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  ToolCallMessage,
  StreamMessage,
  CameraImagesMessage,
  FinishChatMessage,
  ExceptionMessage,
  RuleConfirmMessage,
  AiGeneratedActionsMessage
} from './index';
import {
  getMessageIsCallTool,
  getMessageIsCallToolResult,
  getMessageIsToastStream,
  getMessageIsCameraImages,
  getMessageIsException,
  getMessageIsFinishChat,
  getMessageIsSaveRuleConfirm,
  getMessageIsSaveRuleConfirmResult,
  getMessageIsAiGeneratedActions
} from '@/utils/instruction/typeUtils';


const MessageRenderer = React.memo(({ messageData, allMessages = []}) => {
  const { t } = useTranslation();
  if (!messageData?.header) {
    return null;
  }

  const { header, payload } = messageData;
  const { type, namespace, name } = header;

  let parsedPayload;
  try {
    parsedPayload = JSON.parse(payload);
  } catch (error) {
    return (
      <div style={{ color: 'red', fontSize: '12px' }}>
        {t('instant.chat.messageParseFailed')}{payload}
      </div>
    );
  }

  // render by message type
  if(getMessageIsCallTool(type, namespace, name)) {
    return <ToolCallMessage data={parsedPayload} allMessages={allMessages} />;
  }
  if(getMessageIsCallToolResult(type, namespace, name)) {
    return null
  }
  if(getMessageIsToastStream(type, namespace, name)) {
    return <StreamMessage data={parsedPayload} isAccumulating={messageData.isAccumulating || false} />;
  }
  if(getMessageIsCameraImages(type, namespace, name)) {
    return <CameraImagesMessage data={parsedPayload} />;
  }
  if(getMessageIsException(type, namespace, name)) {
    return <ExceptionMessage data={parsedPayload} />;
  }
  if(getMessageIsFinishChat(type, namespace, name)) {
    return <FinishChatMessage data={parsedPayload} />;
  }
  if(getMessageIsSaveRuleConfirm(type, namespace, name)) {
    return <RuleConfirmMessage data={parsedPayload} mode="queryEdit" />;
  }
  if(getMessageIsSaveRuleConfirmResult(type, namespace, name)) {
    return <RuleConfirmMessage data={parsedPayload} mode="readonly" />;
  }
  if(getMessageIsAiGeneratedActions(type, namespace, name)) {
    return <AiGeneratedActionsMessage data={parsedPayload} />;
  }
  // unknown message type
  return (
    <div style={{
      fontSize: '12px',
      color: '#999',
      padding: '4px 8px',
      backgroundColor: '#f5f5f5',
      borderRadius: '4px'
    }}>
      {t('instant.chat.unknownMessageType')}{namespace}.{name}
    </div>
  );
}, (prevProps, nextProps) => {
  return (
    prevProps.messageData?.header?.request_id === nextProps.messageData?.header?.request_id &&
    prevProps.messageData?.header?.timestamp === nextProps.messageData?.header?.timestamp &&
    prevProps.messageData?.payload === nextProps.messageData?.payload &&
    prevProps.allMessages?.length === nextProps.allMessages?.length
  );
});

// add blink animation style
const style = document.createElement('style');
style.textContent = `
  @keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
  }
`;
document.head.appendChild(style);

export default MessageRenderer;
