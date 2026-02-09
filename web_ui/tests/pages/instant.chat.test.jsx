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

vi.mock('antd', async (importOriginal) => {
  const mod = await importOriginal();
  return {
    ...mod,
    Button: ({ children, onClick, disabled, type, className, icon, ...rest }) => (
      <button
        onClick={onClick}
        disabled={disabled}
        type={type}
        className={className}
        data-testid={rest['data-testid'] || 'antd-button'}
        {...rest}
      >
        {icon}
        {children}
      </button>
    ),
    Flex: ({ children, ...rest }) => <div {...rest}>{children}</div>,
    Tooltip: ({ children, title }) => <div title={title}>{children}</div>,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  };
});

vi.mock('@ant-design/x', () => ({
  Sender: ({ value, onChange, onSubmit, loading, disabled, placeholder, prefix, footer }) => {
    const [localValue, setLocalValue] = React.useState(value || '');

    React.useEffect(() => {
      setLocalValue(value || '');
    }, [value]);

    const handleChange = (e) => {
      const newValue = e.target.value;
      setLocalValue(newValue);
      onChange?.(newValue);
    };

    const handleSubmit = (e) => {
      e?.preventDefault?.();
      if (onSubmit && localValue?.trim()) {
        onSubmit(localValue);
      }
    };

    return (
      <div data-testid="sender-component">
        {prefix && <div data-testid="sender-prefix">{prefix}</div>}
        <textarea
          data-testid="sender-input"
          value={localValue}
          onChange={handleChange}
          placeholder={placeholder}
          disabled={disabled}
        />
        {footer && footer({
          components: {
            SendButton: ({ children, onClick, disabled: btnDisabled, ...props }) => {
              const handleClick = (e) => {
                if (onClick) {
                  onClick(e);
                } else {
                  handleSubmit(e);
                }
              };
              return (
                <button
                  data-testid="send-button"
                  onClick={handleClick}
                  disabled={btnDisabled || loading || !localValue?.trim()}
                  {...props}
                >
                  {children}
                </button>
              );
            },
            LoadingButton: ({ onClick, ...props }) => (
              <button
                data-testid="loading-button"
                onClick={onClick}
                {...props}
              >
                Loading...
              </button>
            ),
          },
        })}
      </div>
    );
  },
}));

vi.mock('@/components', () => ({
  Icon: ({ name, size, color, onClick }) => (
    <span
      data-testid={`icon-${name}`}
      data-size={size}
      data-color={color}
      onClick={onClick}
    >
      {name}
    </span>
  ),
}));

vi.mock('@/pages/Instant/components/Send/components/SelectedItemsPrefix', () => ({
  default: () => <div data-testid="selected-items-prefix" />,
}));

vi.mock('@/pages/Instant/components/Send/components/BottomControlButtons', () => ({
  default: () => <div data-testid="bottom-control-buttons" />,
}));

const mockSetIsAnswering = vi.fn();
const mockSetCurrentAnswer = vi.fn();
const mockGlobalSendMessage = vi.fn();
const mockStartNewRound = vi.fn();

let mockStoreState = {
  input: '',
  isAnswering: false,
  currentAnswer: null,
  answerMessages: [],
  isSocketActive: false,
};

const mockSetInput = vi.fn((value) => {
  mockStoreState.input = value;
});

const createMockChatStore = (overrides = {}) => ({
  ...mockStoreState,
  ...overrides,
  setInput: mockSetInput,
  setIsAnswering: mockSetIsAnswering,
  setCurrentAnswer: mockSetCurrentAnswer,
  globalSendMessage: mockGlobalSendMessage,
  startNewRound: mockStartNewRound,
});

vi.mock('@/stores/chatStore', async (importOriginal) => {
  const mod = await importOriginal();
  return {
    ...mod,
    useChatStore: vi.fn(() => createMockChatStore()),
  };
});

const mockSendMessage = vi.fn();
const mockGlobalCloseMessage = vi.fn();
const mockSaveStateBeforeLeave = vi.fn();

vi.mock('@/hooks/useGlobalSocket', () => ({
  useGlobalSocket: () => ({
    sendMessage: mockSendMessage,
    globalCloseMessage: mockGlobalCloseMessage,
    saveStateBeforeLeave: mockSaveStateBeforeLeave,
  }),
}));

import { message } from 'antd';
vi.spyOn(message, 'success').mockImplementation(() => {});
vi.spyOn(message, 'error').mockImplementation(() => {});
vi.spyOn(message, 'warning').mockImplementation(() => {});

import Send from '@/pages/Instant/components/Send';
import { useChatStore } from '@/stores/chatStore';

beforeEach(() => {
  mockStoreState = {
    input: '',
    isAnswering: false,
    currentAnswer: null,
    answerMessages: [],
    isSocketActive: false,
  };

  mockSetInput.mockReset();
  mockSetInput.mockImplementation((value) => {
    mockStoreState.input = value;
  });

  mockSetIsAnswering.mockReset();
  mockSetCurrentAnswer.mockReset();
  mockGlobalSendMessage.mockReset();
  mockStartNewRound.mockReset();
  mockSendMessage.mockReset();
  mockGlobalCloseMessage.mockReset();
  mockSaveStateBeforeLeave.mockReset();
  (message.success).mockClear();
  (message.error).mockClear();
  (message.warning).mockClear();

  vi.mocked(useChatStore).mockReturnValue(createMockChatStore());
});

describe('pages/Instant/components/Send', () => {
  it('send message and empty input intercept', async () => {
    const { rerender } = render(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    const input = screen.getByTestId('sender-input');
    let sendButton = screen.getByTestId('send-button');

    expect(input).toBeInTheDocument();
    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: '   ' } });
    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({ input: '   ' })
    );
    rerender(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);
    sendButton = screen.getByTestId('send-button');
    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: 'test message' } });
    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({ input: 'test message' })
    );
    rerender(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);
    sendButton = screen.getByTestId('send-button');
    expect(sendButton).not.toBeDisabled();

    fireEvent.change(input, { target: { value: '' } });
    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({ input: '' })
    );
    rerender(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);
    sendButton = screen.getByTestId('send-button');
    expect(sendButton).toBeDisabled();

    expect(mockGlobalSendMessage).not.toHaveBeenCalled();
  });

  it('normal send message flow', async () => {
    const mockOpenTimeoutGoToBottom = vi.fn();
    const mockMessageData = {
      query: 'test message',
      camera_ids: [],
      mcp_list: [],
    };

    mockGlobalSendMessage.mockResolvedValueOnce(mockMessageData);
    mockSendMessage.mockReturnValueOnce('request-123');

    const { rerender } = render(<Send openTimeoutGoToBottom={mockOpenTimeoutGoToBottom} clearTimeoutGoToBottom={vi.fn()} />);

    const input = screen.getByTestId('sender-input');

    fireEvent.change(input, { target: { value: 'test message' } });

    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({ input: 'test message' })
    );
    rerender(<Send openTimeoutGoToBottom={mockOpenTimeoutGoToBottom} clearTimeoutGoToBottom={vi.fn()} />);

    await waitFor(() => {
      const sendButton = screen.getByTestId('send-button');
      expect(sendButton).not.toBeDisabled();
    });

    const sendButton = screen.getByTestId('send-button');
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(mockGlobalSendMessage).toHaveBeenCalledWith(
        'test message',
        null,
        expect.objectContaining({
          onBeforeSend: expect.any(Function),
        })
      );

      expect(mockSendMessage).toHaveBeenCalledWith(mockMessageData);

      expect(mockOpenTimeoutGoToBottom).toHaveBeenCalled();
    });
  });

  it('when answering, cannot send new message', async () => {
    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({
        input: 'test message',
        isAnswering: true,
      })
    );

    render(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    const input = screen.getByTestId('sender-input');
    const loadingButton = screen.getByTestId('loading-button');
    const sendButton = screen.queryByTestId('send-button');

    expect(loadingButton).toBeInTheDocument();
    expect(sendButton).not.toBeInTheDocument();

    expect(input.value).toBe('test message');

    mockGlobalSendMessage.mockResolvedValueOnce(null);

    await waitFor(() => {
      expect(mockGlobalSendMessage).not.toHaveBeenCalled();
    });
  });

  it('when click stop button, can stop message processing', async () => {
    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({
        isAnswering: true,
      })
    );

    render(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    const loadingButton = screen.getByTestId('loading-button');

    fireEvent.click(loadingButton);

    await waitFor(() => {
      expect(mockGlobalCloseMessage).toHaveBeenCalled();
    });
  });

  it('when send message failed, show error message', async () => {
    const mockMessageData = {
      query: 'test message',
      camera_ids: [],
      mcp_list: [],
    };

    mockGlobalSendMessage.mockResolvedValueOnce(mockMessageData);
    mockSendMessage.mockImplementationOnce(() => {
      throw new Error('send failed');
    });

    const { rerender } = render(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    const input = screen.getByTestId('sender-input');

    fireEvent.change(input, { target: { value: 'test message' } });

    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({ input: 'test message' })
    );
    rerender(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    await waitFor(() => {
      const sendButton = screen.getByTestId('send-button');
      expect(sendButton).not.toBeDisabled();
    });

    const sendButton = screen.getByTestId('send-button');
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(mockGlobalSendMessage).toHaveBeenCalled();
      expect(mockSendMessage).toHaveBeenCalledWith(mockMessageData);
      expect(message.error).toHaveBeenCalledWith('instant.chat.sendMessageFailed');
      expect(mockSetIsAnswering).toHaveBeenCalledWith(false);
    });
  });

  it('when input content changes, update store', () => {
    render(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={vi.fn()} />);

    const input = screen.getByTestId('sender-input');

    fireEvent.change(input, { target: { value: 'new message' } });

    expect(mockSetInput).toHaveBeenCalledWith('new message');
  });

  it('when socket is not active, clear auto scroll timer', () => {
    const mockClearTimeoutGoToBottom = vi.fn();

    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({
        isSocketActive: true,
      })
    );

    const { rerender } = render(
      <Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={mockClearTimeoutGoToBottom} />
    );

    vi.mocked(useChatStore).mockReturnValue(
      createMockChatStore({
        isSocketActive: false,
      })
    );

    rerender(<Send openTimeoutGoToBottom={vi.fn()} clearTimeoutGoToBottom={mockClearTimeoutGoToBottom} />);

    expect(mockClearTimeoutGoToBottom).toHaveBeenCalled();
  });
});

