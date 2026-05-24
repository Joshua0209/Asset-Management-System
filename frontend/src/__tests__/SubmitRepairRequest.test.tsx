import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SubmitRepairRequest from '@/pages/holder/SubmitRepairRequest';
import { ConfigProvider, message } from 'antd';
import { ApiError, assetsApi, repairRequestsApi } from '@/api';
import type { RepairRequestRecord } from '@/api/repair-requests';
import { buildAssetResponse } from './test-helpers';

// Mock i18next — preserve real exports (e.g. initReactI18next, used by
// src/i18n/index.ts when format.ts is loaded transitively) and only stub
// useTranslation so component output is deterministic.
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  };
});

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

function fileInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('Upload input not rendered');
  return input;
}

describe('SubmitRepairRequest', () => {
  let messageErrorSpy: MockInstance<typeof message.error>;
  let messageSuccessSpy: MockInstance<typeof message.success>;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    messageErrorSpy = vi.spyOn(message, 'error').mockImplementation(() => null as never);
    messageSuccessSpy = vi.spyOn(message, 'success').mockImplementation(() => null as never);
  });

  afterEach(() => {
    messageErrorSpy.mockRestore();
    messageSuccessSpy.mockRestore();
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

  it('shows the generic error message when submit rejects with a non-ApiError', async () => {
    mockListMyAssets.mockResolvedValue(ASSETS_RESPONSE);
    const submitError = new Error('network down');
    mockSubmitRepairRequest.mockRejectedValue(submitError);
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderPage();
    await selectFirstAsset();

    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });
    fireEvent.click(screen.getByText('common.repairRequest.submit'));

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith('common.repairRequest.errorMessage');
    });
    // Pin the exact ``console.error('Submission error:', error)`` call shape.
    // A regression that drops the prefix, swaps the order, or rewraps the
    // original Error would otherwise pass with the looser .toHaveBeenCalled().
    expect(consoleErrorSpy).toHaveBeenCalledWith('Submission error:', submitError);
    consoleErrorSpy.mockRestore();
  });

  it('surfaces the ApiError branch via getApiErrorMessage when submit rejects with an ApiError', async () => {
    // The ApiError branch of the submit catch in SubmitRepairRequest.tsx
    // routes through getApiErrorMessage(error, t), not the generic
    // 'common.repairRequest.errorMessage' key. A regression that conflates
    // the two branches would silently drop server-side conflict messages.
    mockListMyAssets.mockResolvedValue(ASSETS_RESPONSE);
    mockSubmitRepairRequest.mockRejectedValue(
      new ApiError(409, 'conflict', 'Repair request already exists'),
    );

    renderPage();
    await selectFirstAsset();

    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });
    fireEvent.click(screen.getByText('common.repairRequest.submit'));

    await waitFor(() => {
      // getApiErrorMessage maps code='conflict' to t('errors.conflict'),
      // which the i18n stub returns verbatim as the key.
      expect(messageErrorSpy).toHaveBeenCalledWith('errors.conflict');
    });
    expect(messageErrorSpy).not.toHaveBeenCalledWith('common.repairRequest.errorMessage');
  });

  it('beforeUpload rejects non-image files with the format error', async () => {
    mockAssetsListThen('success');
    renderPage();

    await waitFor(() => expect(fileInput()).toBeDefined());
    const badFile = new File(['hello'], 'note.txt', { type: 'text/plain' });
    fireEvent.change(fileInput(), { target: { files: [badFile] } });

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith('common.repairRequest.uploadFormat');
    });
    // Rejected files do not show up in the Upload list.
    expect(screen.queryByText('note.txt')).toBeNull();
  });

  it('beforeUpload rejects files larger than 5 MB with the size error', async () => {
    mockAssetsListThen('success');
    renderPage();

    await waitFor(() => expect(fileInput()).toBeDefined());
    const oversized = new File([new Uint8Array(6 * 1024 * 1024)], 'big.jpg', {
      type: 'image/jpeg',
    });
    fireEvent.change(fileInput(), { target: { files: [oversized] } });

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith('common.repairRequest.uploadSize');
    });
  });

  it('accepts a valid JPEG via beforeUpload + onChange and submits it as an image part', async () => {
    mockAssetsListThen('success');
    renderPage();

    await selectFirstAsset();
    fireEvent.change(screen.getByLabelText('common.repairRequest.faultDescription'), {
      target: { value: 'Broken screen' },
    });

    const goodFile = new File([new Uint8Array(10)], 'photo.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput(), { target: { files: [goodFile] } });

    fireEvent.click(screen.getByText('common.repairRequest.submit'));

    await waitFor(() => {
      expect(mockSubmitRepairRequest).toHaveBeenCalledWith(expect.any(FormData));
    });

    const formData = mockSubmitRepairRequest.mock.calls[0][0];
    const images = formData.getAll('images');
    expect(images).toHaveLength(1);
    expect((images[0] as File).name).toBe('photo.jpg');
  });
});
