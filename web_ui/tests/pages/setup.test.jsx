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

vi.mock('@/components', () => ({
  ContentModal: ({ children }) => <div data-testid="content-modal">{children}</div>,
  LanguageSwitcher: () => <div data-testid="language-switcher" />,
}));

const mockSetInitPinCode = vi.fn();
vi.mock('@/api', () => ({
  setInitPinCode: (...args) => mockSetInitPinCode(...args),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => { });
vi.spyOn(message, 'error').mockImplementation(() => { });

import Setup from '@/pages/Setup';

async function typePins(pin, confirm) {
  const pinInput = await screen.findByPlaceholderText('login.inputPinPlaceholder');
  const confirmInput = await screen.findByPlaceholderText('login.confirmPinPlaceholder');
  fireEvent.change(pinInput, { target: { value: pin } });
  fireEvent.change(confirmInput, { target: { value: confirm } });
}

beforeEach(() => {
  mockNavigate.mockReset();
  mockSetInitPinCode.mockReset();
  (message.success).mockClear();
  (message.error).mockClear();
});

describe('pages/Setup', () => {
  it('password length is less than 6, show error message and not call interface', async () => {
    render(<Setup />);
    await typePins('12345', '12345');
    const confirmBtn = await screen.findByRole('button', { name: 'login.confirmSetButton' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(message.error).toHaveBeenCalled();
      expect(mockSetInitPinCode).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  it('two inputs are not the same, show error message and not call interface', async () => {
    render(<Setup />);
    await typePins('123456', '123455');
    const confirmBtn = await screen.findByRole('button', { name: 'login.confirmSetButton' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(message.error).toHaveBeenCalled();
      expect(mockSetInitPinCode).not.toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  it('set success, show success message and redirect to /login', async () => {
    mockSetInitPinCode.mockResolvedValueOnce({ code: 0 });
    render(<Setup />);
    await typePins('123456', '123456');
    const confirmBtn = await screen.findByRole('button', { name: 'login.confirmSetButton' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockSetInitPinCode).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
  });

  it('set failed, show error message and not redirect', async () => {
    mockSetInitPinCode.mockResolvedValueOnce({ code: 1 });
    render(<Setup />);
    await typePins('123456', '123456');
    const confirmBtn = await screen.findByRole('button', { name: 'login.confirmSetButton' });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockSetInitPinCode).toHaveBeenCalled();
      expect(message.error).toHaveBeenCalled();
      expect(mockNavigate).not.toHaveBeenCalledWith('/login');
    });
  });
});

