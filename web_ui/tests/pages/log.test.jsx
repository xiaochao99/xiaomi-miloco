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
  Card: ({ children, className, contentClassName }) => (
    <div data-testid="card" className={className}>
      <div className={contentClassName}>{children}</div>
    </div>
  ),
  PageContent: ({ Header: HeaderNode, children, showEmptyContent, emptyContentProps }) => (
    <div data-testid="page-content">
      {HeaderNode}
      {showEmptyContent ? (
        <div>{emptyContentProps?.description}</div>
      ) : (
        children
      )}
    </div>
  ),
  Icon: ({ name, onClick }) => (
    <button data-testid={`icon-${name}`} onClick={onClick} />
  ),
  LogViewerModal: () => null,
}));

vi.mock('@/stores/logViewerStore', () => ({
  useLogViewerStore: () => ({
    openModalWithLogId: vi.fn(),
  }),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...actual,
    Table: ({ dataSource, columns, locale }) => (
      <div data-testid="table">
        {dataSource && dataSource.length > 0 ? (
          <div>
            {dataSource.map((record, index) => (
              <div key={index} data-testid={`table-row-${index}`}>
                {columns.map((col) => {
                  const content = col.render
                    ? col.render(null, record, index)
                    : record[col.dataIndex];
                  return (
                    <div key={col.key} data-testid={`table-cell-${col.key}`}>
                      {typeof content === 'string' ? content : <div>{content}</div>}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        ) : (
          <div>{locale?.emptyText}</div>
        )}
      </div>
    ),
    Empty: ({ description }) => <div>{description}</div>,
    Button: ({ children, onClick }) => <button onClick={onClick}>{children}</button>,
  };
});

const mockGetRuleTriggerLogs = vi.fn();
const mockGetSmartRules = vi.fn();
vi.mock('@/api', () => ({
  getRuleTriggerLogs: (...args) => mockGetRuleTriggerLogs(...args),
  getSmartRules: (...args) => mockGetSmartRules(...args),
}));

import LogManage from '@/pages/LogManage';

beforeEach(() => {
  mockGetRuleTriggerLogs.mockReset();
  mockGetSmartRules.mockReset();
});

describe('pages/LogManage', () => {
  it('initialize load, display title, statistics card numbers and table data, and can click refresh', async () => {
    const now = Date.now();
    mockGetRuleTriggerLogs.mockResolvedValueOnce({
      code: 0,
      data: {
        total_items: 5,
        rule_logs: [
          {
            id: 'log-1',
            timestamp: now,
            trigger_rule_name: 'Rule A',
            trigger_rule_condition: 'if A',
            condition_results: [
              {
                camera_info: { name: 'Cam1' },
                channel: 1,
                result: true,
                images: [{ data: 'http://example.com/a.jpg', timestamp: now }],
              },
            ],
            execute_result: {
              ai_recommend_execute_type: 'static',
              ai_recommend_action_execute_results: [
                {
                  action: {
                    mcp_server_name: 'server1',
                    introduction: 'Action X',
                  },
                  result: true,
                },
              ],
              automation_action_execute_results: [],
              notify_result: {
                notify: { content: 'Notify Y' },
                result: false,
              },
            },
          },
        ],
      },
    });
    mockGetSmartRules.mockResolvedValueOnce({
      data: [
        { enabled: true },
        { enabled: false },
      ],
    });

    render(<LogManage />);

    expect(await screen.findByText('home.menu.logManage')).toBeInTheDocument();

    expect(await screen.findByText('5')).toBeInTheDocument();
    expect(await screen.findByText('1')).toBeInTheDocument();

    expect(await screen.findByText('Rule A')).toBeInTheDocument();
    expect(await screen.findByText('if A')).toBeInTheDocument();
    expect(await screen.findByText('Action X')).toBeInTheDocument();
    expect(await screen.findByText(/logManage.sendNotification/)).toBeInTheDocument();

    mockGetRuleTriggerLogs.mockResolvedValueOnce({ code: 0, data: { total_items: 5, rule_logs: [] } });
    mockGetSmartRules.mockResolvedValueOnce({ data: [{ enabled: true }] });

    const refreshBtn = await screen.findByTestId('icon-refresh');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetRuleTriggerLogs).toHaveBeenCalledTimes(2);
      expect(mockGetSmartRules).toHaveBeenCalledTimes(2);
    });
  });

  it('no data, show empty state', async () => {
    mockGetRuleTriggerLogs.mockResolvedValueOnce({ code: 0, data: { total_items: 0, rule_logs: [] } });
    mockGetSmartRules.mockResolvedValueOnce({ data: [] });

    render(<LogManage />);

    expect(await screen.findByText('home.menu.logManage')).toBeInTheDocument();
    expect(await screen.findByText('logManage.noRuleRecord')).toBeInTheDocument();
  });
});

