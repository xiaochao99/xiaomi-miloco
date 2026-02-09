/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k) => k }),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const mod = await importOriginal();
  return {
    ...mod,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('antd', async (importOriginal) => {
  const mod = await importOriginal();
  return {
    ...mod,
    Input: {
      ...mod.Input,
      OTP: ({ onChange }) => (
        <input data-testid="otp" onChange={(e) => onChange?.(e.target.value)} />
      ),
    },
  };
});

vi.mock('@/components', () => ({
  ContentModal: ({ children }) => <div data-testid="content-modal">{children}</div>,
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
}));

const mockGetJudgeLogin = vi.fn();
const mockGetPinLogin = vi.fn();
vi.mock('@/api', () => ({
  getJudgeLogin: (...args) => mockGetJudgeLogin(...args),
  getPinLogin: (...args) => mockGetPinLogin(...args),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => { });
vi.spyOn(message, 'error').mockImplementation(() => { });

import Login from '@/pages/Login';

async function typeSixDigitPin() {
  const otp = await screen.findByTestId('otp');
  fireEvent.change(otp, { target: { value: '123456' } });
}

beforeEach(() => {
  mockNavigate.mockReset();
  mockGetJudgeLogin.mockReset();
  mockGetPinLogin.mockReset();
  (message.success).mockClear();
  (message.error).mockClear();
});

describe('pages/Login', () => {
  it('if not registered, redirect to /setup', async () => {
    mockGetJudgeLogin.mockResolvedValueOnce({ code: 0, data: { is_registered: false } });
    render(<Login />);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/setup');
    });
  });

  it('password is correct, login success, show success message and redirect to /home', async () => {
    mockGetJudgeLogin.mockResolvedValueOnce({ code: 0, data: { is_registered: true } });
    mockGetPinLogin.mockResolvedValueOnce({ code: 0 });

    render(<Login />);

    await typeSixDigitPin();

    const loginBtn = await screen.findByRole('button', { name: 'login.login' });
    fireEvent.click(loginBtn);

    await waitFor(() => {
      expect(mockGetPinLogin).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/home');
    });
  });

  it('password is incorrect, login failed, show error message and not redirect', async () => {
    mockGetJudgeLogin.mockResolvedValueOnce({ code: 0, data: { is_registered: true } });
    mockGetPinLogin.mockResolvedValueOnce({ code: 1 });

    render(<Login />);

    await typeSixDigitPin();
    const loginBtn = await screen.findByRole('button', { name: 'login.login' });
    fireEvent.click(loginBtn);

    await waitFor(() => {
      expect(mockGetPinLogin).toHaveBeenCalled();
      expect(message.error).toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalledWith('/home');
    });
  });
});

