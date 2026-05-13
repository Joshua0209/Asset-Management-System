import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SubmitRepairRequest from '@/pages/holder/SubmitRepairRequest';
import { ConfigProvider } from 'antd';
import { ApiError, apiClient } from '@/api';
import { buildAssetResponse } from './test-helpers';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockRequest = vi.spyOn(apiClient, 'request');

const ASSETS_RESPONSE = buildAssetResponse('AST-2026-00003', 'Latitude 7440', 1);
const ASSET = ASSETS_RESPONSE.data[0];

type AxiosLikeConfig = { url?: string; method?: string };

function mockAssetsListThen(postBehavior: 'success' | ApiError) {
  mockRequest.mockImplementation((config: AxiosLikeConfig) => {
    if (config.url === '/assets/mine') {
      return Promise.resolve({ data: ASSETS_RESPONSE }) as never;
    }
    if (config.url === '/repair-requests') {
      if (postBehavior === 'success') {
        return Promise.resolve({ data: { data: { id: 'test-id' } } }) as never;
      }
      return Promise.reject(postBehavior) as never;
    }
    return Promise.reject(new Error(`Unexpected request to ${config.url}`)) as never;
  });
}

async function selectFirstAsset() {
  const user = userEvent.setup({ delay: null });
  await waitFor(() => {
    expect(screen.getByRole('combobox')).not.toHaveAttribute('disabled');
  });
  await user.click(screen.getByRole('combobox'));
  await user.click(await screen.findByText(`${ASSET.asset_code} — ${ASSET.name}`));
  return user;
}

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ConfigProvider>
        <SubmitRepairRequest />
      </ConfigProvider>
    </MemoryRouter>
  );
}

describe('SubmitRepairRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders form fields', async () => {
    mockAssetsListThen('success');
    renderPage();

    expect(screen.getByLabelText('common.repairRequest.assetId')).toBeDefined();
    expect(screen.getByLabelText('common.repairRequest.faultDescription')).toBeDefined();
    expect(screen.getByText('common.repairRequest.submit')).toBeDefined();

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        expect.objectContaining({ url: '/assets/mine' }),
      );
    });
  });

  it('shows validation errors for empty fields', async () => {
    mockAssetsListThen('success');
    renderPage();

    const submitBtn = screen.getByText('common.repairRequest.submit');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getAllByText('validation.required')).toHaveLength(2);
    });
  });

  it('submits the selected asset UUID, not its code', async () => {
    mockAssetsListThen('success');
    renderPage();

    await selectFirstAsset();

    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });

    fireEvent.click(screen.getByText('common.repairRequest.submit'));

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'POST',
          url: '/repair-requests',
          data: expect.any(FormData),
        }),
      );
    });

    const postCall = mockRequest.mock.calls.find(
      ([config]) => (config as AxiosLikeConfig).url === '/repair-requests',
    );
    const formData = (postCall![0] as { data: FormData }).data;
    expect(formData.get('asset_id')).toBe(ASSET.id);
    expect(formData.get('fault_description')).toBe('Broken screen');
  });

  it('handles submission error', async () => {
    mockAssetsListThen(new ApiError(500, 'internal_error', 'Internal Server Error'));
    renderPage();

    await selectFirstAsset();

    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });

    fireEvent.click(screen.getByText('common.repairRequest.submit'));

    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith(
        expect.objectContaining({ url: '/repair-requests' }),
      );
    });
  });
});
