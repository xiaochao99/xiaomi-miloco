/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import { create } from 'zustand';
import { getMessageIsAiGeneratedActions, getMessageIsToastStream } from '@/utils/instruction/typeUtils';
import { generateRequestId } from '@/utils/instruction';
import { MESSAGE_NAMESPACE, MESSAGE_NLP_NAME, MESSAGE_TYPES } from '@/constants/messageTypes';

/**
 * LogViewer Store - 管理日志弹窗状态
 * LogViewer Store - Manage log viewer modal state
 */
export const useLogViewerStore = create((set, get) => ({
  open: false,
  socketMessages: [],
  socketStatus: 'DISCONNECTED', // DISCONNECTED | CONNECTING | CONNECTED | ERROR
  socketRef: null,
  actionDescriptions: [],
  cameras: [],
  mcp_list: [],
  aiGeneratedActions: [],
  cacheActions: [],
  _connectWebSocket: ({ endpoint, params, onOpenCallback, reconnectCallback, initialState = {} }) => {
    const state = get();

    set({
      open: true,
      socketMessages: [],
      ...initialState
    });

    if (state.socketRef?.readyState === WebSocket.OPEN || state.socketRef?.readyState === WebSocket.CONNECTING) {
      state.socketRef.close();
    }

    set({ socketStatus: 'CONNECTING' });

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const baseUrl = `${wsProtocol}://${window.location.host}${import.meta.env.VITE_API_BASE || ''}${endpoint}`;
    const urlParams = new URLSearchParams(params);
    const wsUrl = `${baseUrl}?${urlParams.toString()}`;

    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      set({ socketStatus: 'CONNECTED' });
      if (onOpenCallback) {
        onOpenCallback(socket);
      }
    };

    socket.onmessage = (event) => {
      try {
        const messageData = JSON.parse(event.data);
        get().addSocketMessage(messageData);
      } catch (error) {
        console.error('parse socket message failed:', error);
      }
    };

    socket.onclose = (event) => {
      console.log('log viewer socket connection closed:', event);
      set({ socketStatus: 'DISCONNECTED' });

      if (event.code !== 1000 && !event.wasClean && get().open) {
        setTimeout(() => {
          if (get().open && reconnectCallback) {
            reconnectCallback();
          }
        }, 3000);
      }
    };

    socket.onerror = (error) => {
      console.error('log viewer socket error:', error);
      set({ socketStatus: 'ERROR' });
    };

    set({ socketRef: socket });
  },

  openModal: (actionDescriptions = [], cameras = [], mcp_list = []) => {
    const requestId = generateRequestId();

    set({ cacheActions: [] });

    get()._connectWebSocket({
      endpoint: '/api/chat/ws/query',
      params: { request_id: requestId },
      initialState: { actionDescriptions, cameras, mcp_list },
      onOpenCallback: (socket) => {
        if (socket.readyState === WebSocket.OPEN) {
          const currentState = get();
          socket.send(JSON.stringify({
            header: {
              type: MESSAGE_TYPES.EVENT,
              namespace: MESSAGE_NAMESPACE.NLP,
              name: MESSAGE_NLP_NAME.ACTION_DESCRIPTION_DYNAMIC_EXECUTE,
              timestamp: Math.floor(Date.now() / 1000),
              request_id: requestId,
            },
            payload: JSON.stringify({
              action_descriptions: currentState.actionDescriptions,
              camera_ids: currentState.cameras,
              mcp_list: currentState.mcp_list,
            })
          }));
        }
      },
      reconnectCallback: () => {
        const currentState = get();
        get().openModal(currentState.actionDescriptions, currentState.cameras, currentState.mcp_list);
      }
    });
  },

  openModalWithLogId: (logId) => {
    get()._connectWebSocket({
      endpoint: '/api/trigger/ws/dynamic_execute_log',
      params: { log_id: logId },
      reconnectCallback: () => {
        get().openModalWithLogId(logId);
      }
    });
  },

  closeModal: () => {
    set({ open: false });
    set({ aiGeneratedActions: get().cacheActions || [] });
    const { socketRef } = get();
    if (socketRef) {
      try {
        socketRef.close();
      } catch (error) {
        console.error('close socket connection failed:', error);
      }
    }
    set({ socketRef: null, socketMessages: [], socketStatus: 'DISCONNECTED' });
  },

  addSocketMessage: (messageData) => {
    set((state) => {
      const { header } = messageData;
      const { type, namespace, name } = header;

      if (getMessageIsToastStream(type, namespace, name)) {
        const currentMessages = [...state.socketMessages];
        let lastToastStreamIndex = -1;

        if (currentMessages.length > 0) {
          const lastMsg = currentMessages[currentMessages.length - 1];
          const lastHeader = lastMsg.header;
          if (getMessageIsToastStream(lastHeader.type, lastHeader.namespace, lastHeader.name)) {
            lastToastStreamIndex = currentMessages.length - 1;
          }
        }

        if (lastToastStreamIndex >= 0) {
          const existingMsg = currentMessages[lastToastStreamIndex];
          try {
            const existingPayload = JSON.parse(existingMsg.payload);
            const newPayload = JSON.parse(messageData.payload);

            const accumulatedPayload = {
              ...existingPayload,
              stream: (existingPayload.stream || '') + (newPayload.stream || '')
            };

            currentMessages[lastToastStreamIndex] = {
              ...existingMsg,
              payload: JSON.stringify(accumulatedPayload),
              isAccumulating: true,
              lastUpdated: Date.now()
            };

            return { socketMessages: currentMessages };
          } catch (error) {
            console.error('accumulate ToastStream message failed:', error);
          }
        }
      }

      if (getMessageIsAiGeneratedActions(type, namespace, name)) {
        const payload = JSON.parse(messageData.payload);
        set({ cacheActions: payload.actions });
      }

      return {
        socketMessages: [...state.socketMessages, {
          ...messageData,
          isAccumulating: false,
          lastUpdated: Date.now()
        }]
      };
    });
  },

  clearMessages: () => {
    set({ socketMessages: [] });
  },

  setSocketStatus: (status) => {
    set({ socketStatus: status });
  },

  setSocketRef: (socket) => {
    set({ socketRef: socket });
  },

  getActionDescriptions: () => {
    return get().actionDescriptions;
  },
  setAiGeneratedActions: (actions) => {
    set({ aiGeneratedActions: actions });
  },
}));
