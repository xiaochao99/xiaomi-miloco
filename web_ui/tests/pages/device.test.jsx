/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

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
  Icon: ({ name }) => <span data-testid={`icon-${name}`} />,
}));

const mockGetDeviceList = vi.fn();
const mockRefreshMiotDevices = vi.fn();
vi.mock('@/api', () => ({
  getDeviceList: (...args) => mockGetDeviceList(...args),
  refreshMiotDevices: (...args) => mockRefreshMiotDevices(...args),
}));

import DeviceManage from '@/pages/DeviceManage';

beforeEach(() => {
  mockGetDeviceList.mockReset();
  mockRefreshMiotDevices.mockReset();
});

describe('pages/DeviceManage', () => {
  it('request device list success, render device name and page title', async () => {
    mockGetDeviceList.mockResolvedValueOnce({
      code: 0,
      data: [
        {
          did: 'd1',
          name: 'Device A',
          icon: '',
          room_name: 'Room1',
          home_name: 'Home1',
          online: true,
          is_set_pincode: 0,
        },
      ],
    });

    render(<DeviceManage />);

    await waitFor(() => {
      expect(mockGetDeviceList).toHaveBeenCalled();
    });

    expect(await screen.findByText('home.menu.deviceManage')).toBeInTheDocument();
    expect(await screen.findByText('Device A')).toBeInTheDocument();
  });

  it('no devices, show empty state', async () => {
    mockGetDeviceList.mockResolvedValueOnce({ code: 0, data: [] });

    render(<DeviceManage />);

    expect(await screen.findByText('deviceManage.noDevice')).toBeInTheDocument();
  });
});

