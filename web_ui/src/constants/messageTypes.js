/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

// Socket message types constant definition
export const MESSAGE_TYPES = {
  EVENT: 'event',
  INSTRUCTION: 'instruction',
};

export const MESSAGE_NAMESPACE = {
  NLP: 'Nlp',
  TEMPLATE: 'Template',
  DIALOG: 'Dialog',
  CONFIRMATION: 'Confirmation'
};

// nlp message types
export const MESSAGE_NLP_NAME = {
  REQUEST: 'Request',
  ACTION_DESCRIPTION_DYNAMIC_EXECUTE: 'ActionDescriptionDynamicExecute',
};

// template message types
export const MESSAGE_TEMPLATE_NAME = {
  CALL_TOOL: 'CallTool',
  CALL_TOOL_RESULT: 'CallToolResult',
  TOAST_STREAM: 'ToastStream',
  CAMERA_IMAGES: 'CameraImages'
};

// dialog message types
export const MESSAGE_DIALOG_NAME = {
  EXCEPTION: 'Exception',
  FINISH_CHAT: 'Finish'
};

// rule confirmation message types
export const MESSAGE_CONFIRMATION_NAME = {
  SAVE_RULE_CONFIRM: 'SaveRuleConfirm',
  SAVE_RULE_CONFIRM_RESULT: 'SaveRuleConfirmResult',
  AI_GENERATED_ACTIONS: 'AiGeneratedActions'

};



// message processing status
export const SOCKET_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  ERROR: 'error'
};

