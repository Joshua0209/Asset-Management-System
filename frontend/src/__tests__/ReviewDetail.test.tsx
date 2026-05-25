import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import ReviewDetail from '@/pages/manager/ReviewDetail';
import i18n from '@/i18n';
import type { RepairRequestRecord } from '@/api/repair-requests/types';
import { mockApi } from './test-helpers';

vi.mock('@/components/AuthImage', () => ({
  default: ({ imageId, alt }: { imageId: string; alt?: string }) => (
    <img data-testid={`fault-image-${imageId}`} alt={alt ?? 'Fault'} />
  ),
}));

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
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

const apiModule = await import('@/api');
const mockGetRepairRequestById = vi.mocked(apiModule.repairRequestsApi.getRepairRequestById);
const mockApproveRepairRequest = vi.mocked(apiModule.repairRequestsApi.approveRepairRequest);
const mockRejectRepairRequest = vi.mocked(apiModule.repairRequestsApi.rejectRepairRequest);
const mockUpdateRepairRequestDetails = vi.mocked(
  apiModule.repairRequestsApi.updateRepairRequestDetails,
);
const mockCompleteRepairRequest = vi.mocked(apiModule.repairRequestsApi.completeRepairRequest);
type User = ReturnType<typeof userEvent.setup>;
type RepairDetailInputs = {
  repairDate: string;
  faultDescription: string;
  repairPlan: string;
  repairCost: string;
  repairVendor: string;
};

async function clickButton(user: User, name: string): Promise<void> {
  await act(async () => {
    await user.click(screen.getByRole('button', { name }));
  });
}

async function clickLastButton(user: User, name: string): Promise<void> {
  await act(async () => {
    const buttons = screen.getAllByRole('button', { name });
    await user.click(buttons[buttons.length - 1]);
  });
}

async function typeLabel(user: User, label: string, value: string): Promise<void> {
  await act(async () => {
    await user.type(screen.getByLabelText(label), value);
  });
}

async function performApproveFlow(user: User): Promise<void> {
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  await clickButton(user, 'Approve');
  await typeLabel(user, 'Repair Plan', 'Plan');
  await typeLabel(user, 'Repair Vendor', 'Vendor');
  await typeLabel(user, 'Repair Cost', '100');
  await typeLabel(user, 'Planned Date', '2026-05-01');
  await clickLastButton(user, 'Approve');
}

async function performApproveFlowWithoutCost(user: User): Promise<void> {
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  await clickButton(user, 'Approve');
  await typeLabel(user, 'Repair Plan', 'Plan');
  await typeLabel(user, 'Repair Vendor', 'Vendor');
  await typeLabel(user, 'Planned Date', '2026-05-01');
  await clickLastButton(user, 'Approve');
}

async function performApproveFlowWithoutRepairDetails(user: User): Promise<void> {
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  await clickButton(user, 'Approve');
  await clickLastButton(user, 'Approve');
}

async function fillRepairDetails(user: User, details: RepairDetailInputs): Promise<void> {
  await typeLabel(user, 'Repair Date', details.repairDate);
  await typeLabel(user, 'Fault Description', details.faultDescription);
  await typeLabel(user, 'Repair Plan', details.repairPlan);
  await typeLabel(user, 'Repair Cost', details.repairCost);
  await typeLabel(user, 'Repair Vendor', details.repairVendor);
}

async function submitApproveWithError(error: unknown): Promise<void> {
  const user = userEvent.setup({ delay: null });
  mockGetRepairRequestById.mockResolvedValueOnce(buildRequest('pending_review'));
  mockApproveRepairRequest.mockRejectedValueOnce(error);

  await renderDetailPage();
  await performApproveFlow(user);
}

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

function buildUnderRepairWithDetails(): RepairRequestRecord {
  return {
    ...buildRequest('under_repair'),
    repair_date: '2026-05-08',
    fault_content: 'Thermal paste aged and fan exhaust blocked.',
    repair_plan: 'Clean cooling module and replace thermal paste.',
    repair_cost: null,
    repair_vendor: 'Internal IT Maintenance',
  };
}

async function renderDetailPage(path = '/reviews/rr-1', routePath = '/reviews/:id'): Promise<void> {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={<ReviewDetail />} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

describe('ReviewDetail', () => {
  beforeEach(async () => {
    mockGetRepairRequestById.mockReset();
    mockApproveRepairRequest.mockReset();
    mockRejectRepairRequest.mockReset();
    mockUpdateRepairRequestDetails.mockReset();
    mockCompleteRepairRequest.mockReset();
    mockApi.success.mockReset();
    mockApi.error.mockReset();
    const defaultRequest = buildRequest('pending_review');
    mockApproveRepairRequest.mockResolvedValue(defaultRequest);
    mockRejectRepairRequest.mockResolvedValue(defaultRequest);
    mockUpdateRepairRequestDetails.mockResolvedValue(defaultRequest);
    mockCompleteRepairRequest.mockResolvedValue(defaultRequest);

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

    await performApproveFlow(user);

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
        repair_plan: 'Plan',
        repair_vendor: 'Vendor',
        repair_cost: '100',
        planned_date: '2026-05-01',
      });
    });
  });

  it('allows approval without an estimated repair cost', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('pending_review'))
      .mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await performApproveFlowWithoutCost(user);

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
        repair_plan: 'Plan',
        repair_vendor: 'Vendor',
        planned_date: '2026-05-01',
      });
    });
  });

  it('allows approval without repair detail fields', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('pending_review'))
      .mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await performApproveFlowWithoutRepairDetails(user);

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
      });
    });
  });

  it('moves reject operation to review details page and submits payload', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('pending_review'))
      .mockResolvedValueOnce(buildRequest('rejected'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    });

    await clickButton(user, 'Reject');
    await typeLabel(user, 'Rejection Reason', 'Cannot reproduce');
    await clickLastButton(user, 'Reject');

    await waitFor(() => {
      expect(mockRejectRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
        rejection_reason: 'Cannot reproduce',
      });
    });
  });

  it('moves update-details and complete operations to review details page', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('under_repair'))
      .mockResolvedValueOnce(buildRequest('under_repair'))
      .mockResolvedValueOnce(buildRequest('completed'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Update Details' })).toBeInTheDocument();
    });

    await clickButton(user, 'Update Details');
    await fillRepairDetails(user, {
      repairDate: '2026-04-21',
      faultDescription: 'Connector issue',
      repairPlan: 'Reseat connector',
      repairCost: '1500',
      repairVendor: 'Vendor B',
    });
    await clickButton(user, 'Save');

    await waitFor(() => {
      expect(mockUpdateRepairRequestDetails).toHaveBeenCalledWith(
        'rr-1',
        expect.objectContaining({
          version: 1,
          fault_content: 'Connector issue',
          repair_plan: 'Reseat connector',
        }),
      );
    });

    await clickButton(user, 'Complete');
    await fillRepairDetails(user, {
      repairDate: '2026-04-28',
      faultDescription: 'Resolved',
      repairPlan: 'Replaced part',
      repairCost: '1800',
      repairVendor: 'Vendor C',
    });
    await clickLastButton(user, 'Complete');

    await waitFor(() => {
      expect(mockCompleteRepairRequest).toHaveBeenCalledWith(
        'rr-1',
        expect.objectContaining({
          version: 1,
          repair_vendor: 'Vendor C',
        }),
      );
    });
  });

  it('allows updating a single repair detail field', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('under_repair'))
      .mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Update Details' })).toBeInTheDocument();
    });

    await clickButton(user, 'Update Details');
    await typeLabel(user, 'Repair Vendor', 'Vendor B');
    await clickButton(user, 'Save');

    await waitFor(() => {
      expect(mockUpdateRepairRequestDetails).toHaveBeenCalledWith('rr-1', {
        version: 1,
        repair_vendor: 'Vendor B',
      });
    });
  });

  it('requires at least one field when updating repair details', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById.mockResolvedValueOnce(buildRequest('under_repair'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Update Details' })).toBeInTheDocument();
    });

    await clickButton(user, 'Update Details');
    await clickButton(user, 'Save');

    await waitFor(() => {
      expect(screen.getByText('Please fill in at least one repair field')).toBeInTheDocument();
    });
    expect(mockUpdateRepairRequestDetails).not.toHaveBeenCalled();
  });

  it('omits a blank optional repair cost when updating existing repair details', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildUnderRepairWithDetails())
      .mockResolvedValueOnce(buildUnderRepairWithDetails());

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Update Details' })).toBeInTheDocument();
    });

    await clickButton(user, 'Update Details');
    await clickButton(user, 'Save');

    await waitFor(() => {
      expect(mockUpdateRepairRequestDetails).toHaveBeenCalledWith('rr-1', {
        version: 1,
        repair_date: '2026-05-08',
        fault_content: 'Thermal paste aged and fan exhaust blocked.',
        repair_plan: 'Clean cooling module and replace thermal paste.',
        repair_vendor: 'Internal IT Maintenance',
      });
    });
  });

  it('shows fallback content for completed requests without images', async () => {
    const request = buildRequest('completed');
    request.images = [];

    mockGetRepairRequestById.mockResolvedValueOnce(request);

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText('Repair Result')).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('shows generic error when loading fails with non-api error', async () => {
    mockGetRepairRequestById.mockRejectedValueOnce(new Error('boom'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText('Something went wrong. Please try again later.')).toBeInTheDocument();
    });
  });

  it('shows not-found when route has no request id', async () => {
    await renderDetailPage('/reviews', '/reviews');

    await waitFor(() => {
      expect(screen.getByText('Resource not found')).toBeInTheDocument();
    });
  });

  it('shows a warning modal on 409 conflict error and refreshes data', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('pending_review'))
      .mockResolvedValueOnce(buildRequest('pending_review'));

    mockApproveRepairRequest.mockRejectedValueOnce(
      new apiModule.ApiError(409, 'conflict', 'Conflict occurred'),
    );

    await renderDetailPage();

    await performApproveFlow(user);

    // Wait for conflict dialog
    await waitFor(() => {
      expect(screen.getAllByText('Update Conflict')[0]).toBeInTheDocument();
    });

    // Dismiss the dialog
    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'OK' }));
    });

    // Verify refresh
    await waitFor(() => {
      expect(mockGetRepairRequestById).toHaveBeenCalledTimes(2);
    });
  });

  it('shows a generic error toast for other ApiErrors during action', async () => {
    await submitApproveWithError(new apiModule.ApiError(400, 'validation_error', 'Bad request'));

    await waitFor(() => {
      expect(mockApi.error).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Action failed',
          description: 'Invalid input',
        }),
      );
    });
  });

  it('does nothing if error is not an ApiError in showActionError', async () => {
    await submitApproveWithError(new Error('Non-API error'));

    await waitFor(() => {
      expect(mockApi.error).not.toHaveBeenCalled();
    });

  });

  it('allows zero repair cost when completing a repair', async () => {
    const user = userEvent.setup({ delay: null });
    mockGetRepairRequestById
      .mockResolvedValueOnce(buildRequest('under_repair'))
      .mockResolvedValueOnce(buildRequest('completed'));

    await renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Complete' })).toBeInTheDocument();
    });

    await clickButton(user, 'Complete');
    await typeLabel(user, 'Repair Date', '2026-04-28');
    await typeLabel(user, 'Fault Description','Resolved');
    await typeLabel(user, 'Repair Plan', 'Replaced part');
    await typeLabel(user, 'Repair Cost', '0');
    await typeLabel(user, 'Repair Vendor', 'Vendor C');
    await clickLastButton(user, 'Complete');

    await waitFor(() => {
      expect(mockCompleteRepairRequest).toHaveBeenCalledWith(
        'rr-1',
        expect.objectContaining({
          version: 1,
          repair_cost: '0',
        }),
      );
    });
  });
});
