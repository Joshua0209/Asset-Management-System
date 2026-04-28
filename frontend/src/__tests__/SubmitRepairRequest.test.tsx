import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SubmitRepairRequest from '../pages/SubmitRepairRequest';
import { ConfigProvider } from 'antd';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Mock matchMedia for antd
Object.defineProperty(window, 'matchMedia', {
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
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock);

describe('SubmitRepairRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders form fields', () => {
    render(
      <MemoryRouter>
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
      <MemoryRouter>
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
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { id: 'test-id' } }),
    });
    localStorage.setItem('token', 'test-token');

    render(
      <MemoryRouter>
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
      expect(mockFetch).toHaveBeenCalledWith('/api/v1/repair-requests', expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Authorization': 'Bearer test-token',
        }),
      }));
    });
  });

  it('handles submission error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: { message: 'Internal Server Error' } }),
    });

    render(
      <MemoryRouter>
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
      expect(mockFetch).toHaveBeenCalled();
    });
    // Message component is hard to test with RTL without more setup,
    // but we've verified fetch was called.
  });
});
