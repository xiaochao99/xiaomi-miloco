/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (k) => k }),
}));

vi.mock('@/components', () => ({
    Header: ({ title }) => <h1>{title}</h1>,
    Card: ({ children }) => <div data-testid="card">{children}</div>,
    PageContent: ({ Header: HeaderNode, children }) => (
        <div data-testid="page-content">
            {HeaderNode}
            {children}
        </div>
    ),
    Icon: () => null,
    ModelModal: ({ open, onOk, onCancel, form, editingModel, llmOptions = [], llmLoading }) => {
        if (!open) {return null;}
        if (editingModel) {
            form.setFieldsValue({ name: editingModel.name, baseUrl: editingModel.baseUrl });
        }
        return (
            <div role="dialog" aria-label="model-modal">
                <label>
                    Base URL
                    <input
                        aria-label="Base URL"
                        onChange={(e) => form.setFieldsValue({ baseUrl: e.target.value })}
                    />
                </label>
                <label>
                    API Key
                    <input
                        aria-label="API Key"
                        onChange={(e) => form.setFieldsValue({ apiKey: e.target.value })}
                    />
                </label>
                <label>
                    modelModal.modelName
                    <input
                        aria-label="modelModal.modelName"
                        onChange={(e) => form.setFieldsValue({ name: editingModel ? e.target.value : [e.target.value] })}
                    />
                </label>
                <button type="button" onClick={onOk}>common.confirm</button>
                <button type="button" onClick={onCancel}>common.cancel</button>
                <div>{llmLoading ? 'loading' : ''}</div>
                <div>{llmOptions.length}</div>
            </div>
        );
    },
}));

vi.mock('@/pages/ModelManage/components/ModelItem.jsx', () => ({
    default: ({
        model,
        canEdit = true,
        canDelete = true,
        onEdit,
        onDelete,
        onSetModelLoaded,
    }) => (
        <div data-testid={`model-item-${model.id}`}>
            <span>{model.name}</span>
            {model.local && onSetModelLoaded && (
                <button onClick={() => onSetModelLoaded(model.id, !model.loaded)}>
                    {model.loaded ? 'common.unload' : 'common.load'}
                </button>
            )}
            {canEdit && (
                <button aria-label={`edit-${model.id}`} onClick={() => onEdit?.(model)}>edit</button>
            )}
            {canDelete && (
                <button aria-label={`delete-${model.id}`} onClick={() => onDelete?.(model.id)}>delete</button>
            )}
        </div>
    ),
}));

vi.mock('antd', async (importOriginal) => {
    const mod = await importOriginal();
    const createFormStub = () => {
        const store = {};
        return [{
            setFieldsValue: (vals) => Object.assign(store, vals || {}),
            getFieldValue: (name) => store[name],
            validateFields: async () => ({ ...store }),
        }];
    };
    const FormStub = Object.assign(({ children }) => children, {
        Item: ({ children }) => children,
        useForm: () => createFormStub(),
    });
    const MockSelect = ({ value, onChange, children, ...rest }) => (
        <select aria-label="antd-select" value={value ?? ''} onChange={(e) => onChange?.(e.target.value)} {...rest}>
            {children}
        </select>
    );
    MockSelect.Option = ({ value, disabled, children }) => (
        <option value={value} disabled={disabled}>
            {children}
        </option>
    );
    return {
        ...mod,
        Form: FormStub,
        Select: MockSelect,
    };
});

const mockGetAllModels = vi.fn();
const mockCreateModel = vi.fn();
const mockUpdateModel = vi.fn();
const mockDeleteModel = vi.fn();
const mockGetCudaInfo = vi.fn();
const mockSetModelLoad = vi.fn();
const mockGetModelPurposes = vi.fn();
const mockSetCurrentModel = vi.fn();
const mockGetVendorModels = vi.fn();

vi.mock('@/api', () => ({
    getAllModels: (...args) => mockGetAllModels(...args),
    createModel: (...args) => mockCreateModel(...args),
    updateModel: (...args) => mockUpdateModel(...args),
    deleteModel: (...args) => mockDeleteModel(...args),
    getCudaInfo: (...args) => mockGetCudaInfo(...args),
    setModelLoad: (...args) => mockSetModelLoad(...args),
    getModelPurposes: (...args) => mockGetModelPurposes(...args),
    setCurrentModel: (...args) => mockSetCurrentModel(...args),
    getVendorModels: (...args) => mockGetVendorModels(...args),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => {});
vi.spyOn(message, 'error').mockImplementation(() => {});

import ModelManage from '@/pages/ModelManage';

function setupHappyPathMocks() {
    mockGetModelPurposes.mockResolvedValue({
        code: 0,
        data: [
            { type: 'planning' },
            { type: 'vision_understanding' },
        ],
    });

    const modelsResp = {
        code: 0,
        data: {
            current_model_id: 'cloud-1',
            current_model: { planning: 'cloud-1', vision_understanding: null },
            models: [
                { id: 'local-1', model_name: 'llama-3', api_key: '', base_url: '', local: true, estimate_vram_usage: 2.5, loaded: false },
                { id: 'cloud-1', model_name: 'gpt-4o', api_key: 'k', base_url: 'https://api', local: false, loaded: true },
            ],
        },
    };

    mockGetAllModels.mockResolvedValue(modelsResp);
    mockGetCudaInfo.mockResolvedValue({ code: 0, data: { total: 10, free: 8 } });
}

beforeEach(() => {
    mockGetAllModels.mockReset();
    mockCreateModel.mockReset();
    mockUpdateModel.mockReset();
    mockDeleteModel.mockReset();
    mockGetCudaInfo.mockReset();
    mockSetModelLoad.mockReset();
    mockGetModelPurposes.mockReset();
    mockSetCurrentModel.mockReset();
    mockGetVendorModels.mockReset();
    (message.success).mockClear();
    (message.error).mockClear();
});

describe('pages/ModelManage', () => {
    it('render model list (local and cloud) and page title', async () => {
        setupHappyPathMocks();
        render(<ModelManage />);

        expect(await screen.findByText('home.menu.modalManage')).toBeInTheDocument();
        expect(await screen.findByText('llama-3')).toBeInTheDocument();
        expect(await screen.findByText('gpt-4o')).toBeInTheDocument();
    });

    it('add model (open modal, fill form, submit)', async () => {
        setupHappyPathMocks();
        mockCreateModel.mockResolvedValueOnce({ code: 0 });

        render(<ModelManage />);

        const addBtn = await screen.findByRole('button', { name: 'modelModal.addModel' });
        fireEvent.click(addBtn);

        const baseUrl = await screen.findByLabelText('Base URL');
        const apiKey = await screen.findByLabelText('API Key');
        const nameInput = await screen.findByLabelText('modelModal.modelName');
        fireEvent.change(baseUrl, { target: { value: 'https://v' } });
        fireEvent.change(apiKey, { target: { value: 'sk-xxx' } });
        fireEvent.change(nameInput, { target: { value: 'gemini-1.5' } });

        const okBtn = await screen.findByRole('button', { name: 'common.confirm' });
        fireEvent.click(okBtn);

        await waitFor(() => {
            expect(mockCreateModel).toHaveBeenCalledWith({
                model_names: ['gemini-1.5'],
                base_url: 'https://v',
                api_key: 'sk-xxx',
            });
            expect(message.success).toHaveBeenCalled();
        });
    });

    it('edit cloud model (open edit, modify, submit)', async () => {
        setupHappyPathMocks();
        mockUpdateModel.mockResolvedValueOnce({ code: 0 });

        render(<ModelManage />);

        const editBtn = await screen.findByLabelText('edit-cloud-1');
        fireEvent.click(editBtn);

        const apiKey = await screen.findByLabelText('API Key');
        fireEvent.change(apiKey, { target: { value: 'sk-new' } });

        const okBtn = await screen.findByRole('button', { name: 'common.confirm' });
        fireEvent.click(okBtn);

        await waitFor(() => {
            expect(mockUpdateModel).toHaveBeenCalledWith('cloud-1', {
                model_name: 'gpt-4o',
                base_url: 'https://api',
                api_key: 'sk-new',
            });
            expect(message.success).toHaveBeenCalled();
        });
    });

    it('delete cloud model (click delete and confirm)', async () => {
        setupHappyPathMocks();
        mockDeleteModel.mockResolvedValueOnce({ code: 0 });

        render(<ModelManage />);

        const delBtn = await screen.findByLabelText('delete-cloud-1');
        fireEvent.click(delBtn);

        await waitFor(() => {
            expect(mockDeleteModel).toHaveBeenCalledWith('cloud-1');
            expect(message.success).toHaveBeenCalled();
        });
    });

    it('model setting (change purpose bound model)', async () => {
        setupHappyPathMocks();
        mockSetCurrentModel.mockResolvedValueOnce({ code: 0 });

        render(<ModelManage />);

        const combos = await screen.findAllByRole('combobox');
        fireEvent.change(combos[0], { target: { value: 'cloud-1' } });

        await waitFor(() => {
            expect(mockSetCurrentModel).toHaveBeenCalled();
        });
    });

    it('local model load/unload button logic', async () => {
        setupHappyPathMocks();
        mockSetModelLoad.mockResolvedValueOnce({ code: 0 });

        render(<ModelManage />);

        const loadBtn = await screen.findByRole('button', { name: 'common.load' });
        fireEvent.click(loadBtn);

        await waitFor(() => {
            expect(mockSetModelLoad).toHaveBeenCalledWith({ local_model_name: 'llama-3', load: true });
            expect(message.success).toHaveBeenCalled();
        });
    });
});

