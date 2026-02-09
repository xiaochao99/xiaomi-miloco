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

// mock common components
vi.mock('@/components', () => ({
  Header: ({ title, buttonText, buttonHandleCallback }) => (
    <div>
      <h1>{title}</h1>
      {buttonText ? (
        <button onClick={buttonHandleCallback}>{buttonText}</button>
      ) : null}
    </div>
  ),
  PageContent: ({ Header: HeaderNode, children, showEmptyContent, emptyContentProps }) => (
    <div>
      {HeaderNode}
      {showEmptyContent ? (
        <div>{emptyContentProps?.description}</div>
      ) : (
        children
      )}
    </div>
  ),
  Card: ({ children }) => <div data-testid="card">{children}</div>,
  ListItem: () => null,
}));

// mock ServiceList, provide operable buttons and switch
vi.mock('@/pages/McpService/components/ServiceList', () => ({
  default: ({ services, onSwitch, onEdit, onDelete }) => (
    <div>
      {services.map((s) => (
        <div key={s.id} data-testid={`svc-${s.id}`}>
          <span>{s.name}</span>
          <input
            type="checkbox"
            aria-label={`switch-${s.id}`}
            checked={!!s.enable}
            onChange={(e) => onSwitch(s.id, e.target.checked)}
          />
          <button aria-label={`edit-${s.id}`} onClick={() => onEdit(s)}>edit</button>
          <button aria-label={`delete-${s.id}`} onClick={() => onDelete(s.id)}>delete</button>
        </div>
      ))}
    </div>
  ),
}));

// mock ServiceForm, minimize form behavior, use antd Form fake implementation
vi.mock('antd', async (importOriginal) => {
  const mod = await importOriginal();
  const store = {};
  const createFormStub = () => [{
    setFieldsValue: (vals) => Object.assign(store, vals || {}),
    getFieldValue: (name) => store[name],
    validateFields: async () => ({ ...store }),
    resetFields: () => { Object.keys(store).forEach(k => delete store[k]); },
  }];
  const FormStub = Object.assign(({ children }) => children, {
    Item: ({ children, label }) => <label>{children}</label>,
    useForm: () => createFormStub(),
  });
  return {
    ...mod,
    Form: FormStub,
    Select: ({ children, onChange, value }) => (
      <select aria-label="type" value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>{children}</select>
    ),
    Modal: ({ open, onOk, onCancel, children, okText, cancelText, title }) => (
      open ? (
        <div role="dialog" aria-label="mcp-modal">
          <div>{title}</div>
          {children}
          <button onClick={onOk}>{okText || 'ok'}</button>
          <button onClick={onCancel}>{cancelText || 'cancel'}</button>
        </div>
      ) : null
    ),
    Input: Object.assign(({ 'aria-label': ariaLabel, ...rest }) => (
      <input aria-label={ariaLabel} {...rest} />
    ), { TextArea: (props) => <textarea {...props} /> }),
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

vi.mock('@/pages/McpService/components/ServiceForm', () => ({
  default: ({ modalOpen, editId, form, TYPE_OPTIONS, onOk, onCancel }) => (
    modalOpen ? (
      <div role="dialog" aria-label="mcp-form">
        <label>
          type
          <select aria-label="type" onChange={(e) => form.setFieldsValue({ type: e.target.value })}>
            {TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label>
          name
          <input aria-label="name" onChange={(e) => form.setFieldsValue({ name: e.target.value })} />
        </label>
        <label>
          url
          <input aria-label="url" onChange={(e) => form.setFieldsValue({ url: e.target.value })} />
        </label>
        <label>
          desc
          <input aria-label="desc" onChange={(e) => form.setFieldsValue({ desc: e.target.value })} />
        </label>
        <label>
          token
          <input aria-label="token" onChange={(e) => form.setFieldsValue({ token: e.target.value })} />
        </label>
        <button onClick={onOk}>{editId ? 'common.save' : 'common.add'}</button>
        <button onClick={onCancel}>common.cancel</button>
      </div>
    ) : null
  ),
}));

const mockGetMCPService = vi.fn();
const mockSetMCPService = vi.fn();
const mockUpdateMCPService = vi.fn();
const mockDeleteMCPService = vi.fn();

vi.mock('@/api', () => ({
  getMCPService: (...args) => mockGetMCPService(...args),
  setMCPService: (...args) => mockSetMCPService(...args),
  updateMCPService: (...args) => mockUpdateMCPService(...args),
  deleteMCPService: (...args) => mockDeleteMCPService(...args),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => { });
vi.spyOn(message, 'error').mockImplementation(() => { });

import McpService from '@/pages/McpService';

function setupList(services = []) {
  mockGetMCPService.mockResolvedValue({ code: 0, data: { configs: services } });
}

beforeEach(() => {
  mockGetMCPService.mockReset();
  mockSetMCPService.mockReset();
  mockUpdateMCPService.mockReset();
  mockDeleteMCPService.mockReset();
  (message.success).mockClear();
  (message.error).mockClear();
});

describe('pages/McpService', () => {
  it('render title and empty', async () => {
    setupList([]);
    render(<McpService />);

    expect(await screen.findByText('home.menu.mcpService')).toBeInTheDocument();
    expect(await screen.findByText('mcpService.noServices')).toBeInTheDocument();
  });

  it('add service', async () => {
    setupList([]);
    mockSetMCPService.mockResolvedValueOnce({ code: 0 });

    render(<McpService />);

    const addBtn = await screen.findByRole('button', { name: 'mcpService.addService' });
    fireEvent.click(addBtn);

    fireEvent.change(await screen.findByLabelText('type'), { target: { value: 'http_sse' } });
    fireEvent.change(await screen.findByLabelText('name'), { target: { value: 'svc1' } });
    fireEvent.change(await screen.findByLabelText('url'), { target: { value: 'https://sse' } });

    const confirm = await screen.findByRole('button', { name: 'common.add' });
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(mockSetMCPService).toHaveBeenCalledWith({
        access_type: 'http_sse',
        name: 'svc1',
        description: '',
        provider: '',
        provider_website: '',
        timeout: 20,
        url: 'https://sse',
        request_header_token: '',
        enable: true,
      });
      expect(message.success).toHaveBeenCalled();
    });
  });

  it('edit service and save', async () => {
    setupList([{ id: 's1', name: 'svc1', access_type: 'http_sse', description: 'd', provider_website: '', request_header_token: '', enable: true }]);
    mockUpdateMCPService.mockResolvedValueOnce({ code: 0 });

    render(<McpService />);

    fireEvent.click(await screen.findByLabelText('edit-s1'));

    fireEvent.change(await screen.findByLabelText('desc'), { target: { value: 'd2' } });
    fireEvent.change(await screen.findByLabelText('token'), { target: { value: 'tk' } });

    fireEvent.click(await screen.findByRole('button', { name: 'common.save' }));

    await waitFor(() => {
      expect(mockUpdateMCPService).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();
    });
  });

  it('delete service', async () => {
    setupList([{ id: 's2', name: 'svc2', access_type: 'http_sse', enable: true }]);
    mockDeleteMCPService.mockResolvedValueOnce({ code: 0 });

    render(<McpService />);

    fireEvent.click(await screen.findByLabelText('delete-s2'));

    await waitFor(() => {
      expect(mockDeleteMCPService).toHaveBeenCalledWith('s2');
      expect(message.success).toHaveBeenCalled();
    });
  });

  it('toggle enable switch', async () => {
    setupList([{ id: 's3', name: 'svc3', access_type: 'http_sse', enable: false }]);
    mockUpdateMCPService.mockResolvedValueOnce({ code: 0 });

    render(<McpService />);

    const sw = await screen.findByLabelText('switch-s3');
    fireEvent.click(sw);

    await waitFor(() => {
      expect(mockUpdateMCPService).toHaveBeenCalled();
      expect(message.success).toHaveBeenCalled();
    });
  });
});

