/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

vi.mock('@/components', () => ({
  Header: ({ title, rightContent }) => (
    <div>
      <h1>{title}</h1>
      <div>{rightContent}</div>
    </div>
  ),
  Card: ({ children }) => <div data-testid="card">{children}</div>,
  ListItem: ({ title, rightContent, titleClassName }) => (
    <div>
      <span data-testid="list-title" className={titleClassName}>{title}</span>
      <div>{rightContent}</div>
    </div>
  ),
  Loading: () => <div data-testid="loading" />,
  EmptyContent: ({ description }) => <div>{description}</div>,
  Icon: ({ name, onClick }) => <button data-testid={`icon-${name}`} onClick={onClick} />,
}));

const mockGetMiotSceneActions = vi.fn();
const mockGetHaAutomationActions = vi.fn();
const mockRefreshMiotScenes = vi.fn();
const mockRefreshHaAutomation = vi.fn();
const mockExecuteSceneActions = vi.fn();
const mockSendNotification = vi.fn();

vi.mock('@/api', () => ({
  getMiotSceneActions: (...args) => mockGetMiotSceneActions(...args),
  getHaAutomationActions: (...args) => mockGetHaAutomationActions(...args),
  refreshMiotScenes: (...args) => mockRefreshMiotScenes(...args),
  refreshHaAutomation: (...args) => mockRefreshHaAutomation(...args),
  executeSceneActions: (...args) => mockExecuteSceneActions(...args),
  sendNotification: (...args) => mockSendNotification(...args),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => { });
vi.spyOn(message, 'error').mockImplementation(() => { });
vi.spyOn(message, 'warning').mockImplementation(() => { });

import ExecutionManage from '@/pages/ExecutionManage';

beforeEach(() => {
  mockGetMiotSceneActions.mockReset();
  mockGetHaAutomationActions.mockReset();
  mockRefreshMiotScenes.mockReset();
  mockRefreshHaAutomation.mockReset();
  mockExecuteSceneActions.mockReset();
  mockSendNotification.mockReset();
  (message.success).mockClear();
  (message.error).mockClear();
  (message.warning).mockClear();
});

describe('pages/ExecutionManage', () => {
  it('initialize load and display title and mi home automation list, click execute action', async () => {
    mockGetMiotSceneActions.mockResolvedValueOnce({
      code: 0,
      data: [
        { id: 's1', introduction: 'Scene Action 1' },
      ],
    });
    mockGetHaAutomationActions.mockResolvedValueOnce({ code: 0, data: [] });
    mockExecuteSceneActions.mockResolvedValueOnce({ code: 0, data: [{ result: true }], message: 'ok' });

    render(<ExecutionManage />);

    expect(await screen.findByText('home.menu.executionManage')).toBeInTheDocument();

    expect(await screen.findByText('Scene Action 1')).toBeInTheDocument();

    const titleEl = await screen.findByTestId('list-title');
    const container = titleEl.parentElement;
    const execBtn = container && container.querySelector('button');
    if (execBtn) { fireEvent.click(execBtn); }

    await waitFor(() => {
      expect(mockExecuteSceneActions).toHaveBeenCalledWith([{ id: 's1', introduction: 'Scene Action 1' }]);
    });
  });

  it('switch to HA tab and click refresh, trigger HA refresh and reload', async () => {
    mockGetMiotSceneActions.mockResolvedValueOnce({ code: 0, data: [] });
    mockGetHaAutomationActions.mockResolvedValueOnce({ code: 0, data: [{ id: 'h1', introduction: 'HA Action 1' }] });
    mockRefreshHaAutomation.mockResolvedValueOnce({ code: 0 });
    mockGetHaAutomationActions.mockResolvedValueOnce({ code: 0, data: [{ id: 'h1', introduction: 'HA Action 1' }] });

    render(<ExecutionManage />);

    const haTab = await screen.findByRole('tab', { name: 'executionManage.haAutomationExecution' });
    fireEvent.click(haTab);

    const refreshBtn = await screen.findByTestId('icon-refresh');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockRefreshHaAutomation).toHaveBeenCalled();
    });
  });

  it('switch to notification tab, input text and click send, trigger send notification', async () => {
    mockGetMiotSceneActions.mockResolvedValueOnce({ code: 0, data: [] });
    mockGetHaAutomationActions.mockResolvedValueOnce({ code: 0, data: [] });
    mockSendNotification.mockResolvedValueOnce({ code: 0 });

    render(<ExecutionManage />);

    const notifyTab = await screen.findByRole('tab', { name: 'executionManage.miHomeNotification' });
    fireEvent.click(notifyTab);

    const input = await screen.findByPlaceholderText('executionManage.pleaseEnterNotification');
    fireEvent.change(input, { target: { value: 'hello' } });

    const sendText = await screen.findByText('common.send');
    const sendBtn = sendText.closest('button') || sendText;
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(mockSendNotification).toHaveBeenCalledWith('hello');
    });
  });
});

