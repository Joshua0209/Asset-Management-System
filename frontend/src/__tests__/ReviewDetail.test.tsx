import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import ReviewDetail from '../pages/ReviewDetail';
import i18n from '../i18n';
import type { RepairRequestRecord } from '../api/repair-requests/types';

vi.mock('../components/AuthImage', () => ({
  default: ({ imageId, alt }: { imageId: string; alt?: string }) => (
    <img data-testid={`fault-image-${imageId}`} alt={alt ?? 'Fault'} />
  ),
}));

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    repairRequestsApi: {
      getRepairRequestById: vi.fn(),
      approveRepairRequest: vi.fn(),
      rejectRepairRequest: vi.fn(),
      updateRepairRequestDetails: vi.fn(),
      completeRepairRequest: vi.fn(),
    },
  };
});

const apiModule = await import('../api');
const mockGetRepairRequestById = vi.mocked(apiModule.repairRequestsApi.getRepairRequestById);
const mockApproveRepairRequest = vi.mocked(apiModule.repairRequestsApi.approveRepairRequest);

function buildRequest(status: RepairRequestRecord['status']): RepairRequestRecord {
  return {
    id: 'rr-1',
    asset_id: 'asset-1',
    requester_id: 'holder-1',
    reviewer_id: null,
    status,
    fault_description: 'screen flickers',
    repair_date: null,
    fault_content: null,
    repair_plan: null,
    repair_cost: null,
    repair_vendor: null,
    rejection_reason: null,
    completed_at: null,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    version: 1,
    asset: { id: 'asset-1', asset_code: 'AST-1', name: 'Laptop' },
    requester: { id: 'holder-1', name: 'Holder' },
    reviewer: null,
    images: [
      {
        id: 'img-1',
        url: '/api/v1/images/img-1',
        uploaded_at: '2026-04-01T00:00:00Z',
      },
    ],
  };
}

async function renderDetailPage(): Promise<void> {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={['/reviews/rr-1']}>
        <Routes>
          <Route path="/reviews/:id" element={<ReviewDetail />} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

describe('ReviewDetail', () => {
  beforeEach(async () => {
    mockGetRepairRequestById.mockReset();
    mockApproveRepairRequest.mockReset();
    mockApproveRepairRequest.mockResolvedValue({} as never);

    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });

  it('renders full-page fault details, including uploaded images', async () => {
    mockGetRepairRequestById.mockResolvedValueOnce(buildRequest('pending_review'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Repair Request Details' })).toBeInTheDocument();
    });

    expect(screen.getByText('screen flickers')).toBeInTheDocument();
    expect(screen.getByText('Images')).toBeInTheDocument();
    expect(screen.getByTestId('fault-image-img-1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('moves approve operation to review details page and submits payload', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('pending_review'))
      .mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'Approve' }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText('Repair Plan'), 'Replace panel');
      await user.type(screen.getByLabelText('Repair Vendor'), 'Vendor A');
      await user.type(screen.getByLabelText('Repair Cost'), '2200');
      await user.type(screen.getByLabelText('Planned Date'), '2026-04-25');
      const approveButtons = screen.getAllByRole('button', { name: 'Approve' });
      await user.click(approveButtons[approveButtons.length - 1]);
    });

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
        repair_plan: 'Replace panel',
        repair_vendor: 'Vendor A',
        repair_cost: '2200',
        planned_date: '2026-04-25',
      });
    });
  });

  it('shows update-details and complete actions on under-repair requests', async () => {
    mockGetRepairRequestById.mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Update Details' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Complete' })).toBeInTheDocument();
  });
});
