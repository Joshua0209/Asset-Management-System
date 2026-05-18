import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SubmitRepairRequest from '@/pages/holder/SubmitRepairRequest';
import { ConfigProvider } from 'antd';
import { ApiError, assetsApi, repairRequestsApi } from '@/api';
import type { RepairRequestRecord } from '@/api/repair-requests';
import { buildAssetResponse } from './test-helpers';

// Mock i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const mockListMyAssets = vi.spyOn(assetsApi, 'listMyAssets');
const mockSubmitRepairRequest = vi.spyOn(repairRequestsApi, 'submitRepairRequest');

const ASSETS_RESPONSE = buildAssetResponse('AST-2026-00003', 'Latitude 7440', 1);
const ASSET = ASSETS_RESPONSE.data[0];
const SUBMIT_RESPONSE: RepairRequestRecord = {
  id: 'rr-1',
  asset_id: ASSET.id,
  requester_id: 'holder-1',
  reviewer_id: null,
  status: 'pending_review',
  fault_description: 'Broken screen',
  repair_date: null,
  fault_content: null,
  repair_plan: null,
  repair_cost: null,
  repair_vendor: null,
  rejection_reason: null,
  completed_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  version: 1,
  asset: {
    id: ASSET.id,
    asset_code: ASSET.asset_code,
    name: ASSET.name,
  },
  requester: {
    id: 'holder-1',
    name: 'Holder',
  },
  reviewer: null,
  images: [],
};

function mockAssetsListThen(postBehavior: 'success' | ApiError) {
  mockListMyAssets.mockResolvedValue(ASSETS_RESPONSE);
  if (postBehavior === 'success') {
    mockSubmitRepairRequest.mockResolvedValue(SUBMIT_RESPONSE);
    return;
  }
  mockSubmitRepairRequest.mockRejectedValue(postBehavior);
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
      expect(mockListMyAssets).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'in_use', perPage: 100 }),
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
      expect(mockSubmitRepairRequest).toHaveBeenCalledWith(expect.any(FormData));
    });

    const formData = mockSubmitRepairRequest.mock.calls[0][0];
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
      expect(mockSubmitRepairRequest).toHaveBeenCalledWith(expect.any(FormData));
    });
  });
});
