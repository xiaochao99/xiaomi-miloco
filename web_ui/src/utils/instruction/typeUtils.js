/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import {
  MESSAGE_TYPES,
  MESSAGE_NAMESPACE,
  MESSAGE_NLP_NAME,
  MESSAGE_TEMPLATE_NAME,
  MESSAGE_DIALOG_NAME,
  MESSAGE_CONFIRMATION_NAME
} from '@/constants/messageTypes';

export const getMessageIsEvent = (type) => {
  return type === MESSAGE_TYPES.EVENT;
};

export const getMessageIsInstruction = (type) => {
  return type === MESSAGE_TYPES.INSTRUCTION;
};

export const getMessageIsRequest = (type, namespace, name) => {
  return getMessageIsEvent(type) && namespace === MESSAGE_NAMESPACE.NLP && name === MESSAGE_NLP_NAME.REQUEST;
};

export const getMessageIsCallTool = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.TEMPLATE && name === MESSAGE_TEMPLATE_NAME.CALL_TOOL;
};

export const getMessageIsCallToolResult = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.TEMPLATE && name === MESSAGE_TEMPLATE_NAME.CALL_TOOL_RESULT;
};

export const getMessageIsToastStream = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.TEMPLATE && name === MESSAGE_TEMPLATE_NAME.TOAST_STREAM;
};

export const getMessageIsCameraImages = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.TEMPLATE && name === MESSAGE_TEMPLATE_NAME.CAMERA_IMAGES;
};


export const getMessageIsException = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.DIALOG && name === MESSAGE_DIALOG_NAME.EXCEPTION;
};

export const getMessageIsFinishChat = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.DIALOG && name === MESSAGE_DIALOG_NAME.FINISH_CHAT;
};

export const getMessageIsSaveRuleConfirm = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.CONFIRMATION && name === MESSAGE_CONFIRMATION_NAME.SAVE_RULE_CONFIRM;
};

export const getMessageIsSaveRuleConfirmResult = (type, namespace, name) => {
  return getMessageIsEvent(type) && namespace === MESSAGE_NAMESPACE.CONFIRMATION && name === MESSAGE_CONFIRMATION_NAME.SAVE_RULE_CONFIRM_RESULT;
};

export const getMessageIsAiGeneratedActions = (type, namespace, name) => {
  return getMessageIsInstruction(type) && namespace === MESSAGE_NAMESPACE.CONFIRMATION && name === MESSAGE_CONFIRMATION_NAME.AI_GENERATED_ACTIONS;
};
