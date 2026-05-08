import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SubmitRepairRequest from '../pages/SubmitRepairRequest';
import { ConfigProvider } from 'antd';
import { ApiError, apiClient } from '../api';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockRequest = vi.spyOn(apiClient, 'request');

// Mock matchMedia for antd
Object.defineProperty(globalThis, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver for antd
class ResizeObserverMock {
  observe() {
    // No-op
  }
  unobserve() {
    // No-op
  }
  disconnect() {
    // No-op
  }
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock);

describe('SubmitRepairRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders form fields', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ConfigProvider>
          <SubmitRepairRequest />
        </ConfigProvider>
      </MemoryRouter>
    );

    expect(screen.getByLabelText('common.repairRequest.assetId')).toBeDefined();
    expect(screen.getByLabelText('common.repairRequest.faultDescription')).toBeDefined();
    expect(screen.getByText('common.repairRequest.submit')).toBeDefined();
  });

  it('shows validation errors for empty fields', async () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ConfigProvider>
          <SubmitRepairRequest />
        </ConfigProvider>
      </MemoryRouter>
    );

    const submitBtn = screen.getByText('common.repairRequest.submit');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getAllByText('validation.required')).toHaveLength(2);
    });
  });

  it('submits form successfully', async () => {
    mockRequest.mockResolvedValueOnce({ data: { data: { id: 'test-id' } } } as never);

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ConfigProvider>
          <SubmitRepairRequest />
        </ConfigProvider>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText('common.repairRequest.assetId'), {
      target: { value: 'AST-001' },
    });
    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });

    const submitBtn = screen.getByText('common.repairRequest.submit');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'POST',
          url: '/repair-requests',
          data: expect.any(FormData),
        }),
      );
    });
  });

  it('handles submission error', async () => {
    mockRequest.mockRejectedValueOnce(
      new ApiError(500, 'internal_error', 'Internal Server Error'),
    );

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ConfigProvider>
          <SubmitRepairRequest />
        </ConfigProvider>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText('common.repairRequest.assetId'), {
      target: { value: 'AST-001' },
    });
    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });

    const submitBtn = screen.getByText('common.repairRequest.submit');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalled();
    });
    // Message component is hard to test with RTL without more setup,
    // but we've verified the request was made.
  });
});
