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
type FieldEntry = readonly [label: string, value: string];

const approveFields = {
  full: [
    ['Repair Plan', 'Plan'],
    ['Repair Vendor', 'Vendor'],
    ['Repair Cost', '100'],
    ['Planned Date', '2026-05-01'],
  ],
  withoutCost: [
    ['Repair Plan', 'Plan'],
    ['Repair Vendor', 'Vendor'],
    ['Planned Date', '2026-05-01'],
  ],
  empty: [],
} satisfies Record<string, FieldEntry[]>;

const completedRepairDetails = {
  repairDate: '2026-04-28',
  faultDescription: 'Resolved',
  repairPlan: 'Replaced part',
  repairCost: '1800',
  repairVendor: 'Vendor C',
} satisfies RepairDetailInputs;

const zeroCostCompletedRepairDetails = {
  ...completedRepairDetails,
  repairCost: '0',
} satisfies RepairDetailInputs;

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

async function typeFields(user: User, fields: FieldEntry[]): Promise<void> {
  for (const [label, value] of fields) {
    await typeLabel(user, label, value);
  }
}

async function waitForAction(name: string): Promise<void> {
  await waitFor(() => {
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  });
}

async function submitApprove(user: User, fields: FieldEntry[] = approveFields.full): Promise<void> {
  await waitForAction('Approve');
  await clickButton(user, 'Approve');
  await typeFields(user, fields);
  await clickLastButton(user, 'Approve');
}

function mockRequestSequence(...requests: RepairRequestRecord[]): void {
  for (const request of requests) {
    mockGetRepairRequestById.mockResolvedValueOnce(request);
  }
}

async function renderWithRequests(...requests: RepairRequestRecord[]): Promise<void> {
  mockRequestSequence(...requests);
  await renderDetailPage();
}

async function fillRepairDetails(user: User, details: RepairDetailInputs): Promise<void> {
  await typeLabel(user, 'Repair Date', details.repairDate);
  await typeLabel(user, 'Fault Description', details.faultDescription);
  await typeLabel(user, 'Repair Plan', details.repairPlan);
  await typeLabel(user, 'Repair Cost', details.repairCost);
  await typeLabel(user, 'Repair Vendor', details.repairVendor);
}

async function submitComplete(user: User, details: RepairDetailInputs): Promise<void> {
  await waitForAction('Complete');
  await clickButton(user, 'Complete');
  await fillRepairDetails(user, details);
  await clickLastButton(user, 'Complete');
}

async function submitApproveWithError(error: unknown): Promise<void> {
  const user = userEvent.setup({ delay: null });
  mockGetRepairRequestById.mockResolvedValueOnce(buildRequest('pending_review'));
  mockApproveRepairRequest.mockRejectedValueOnce(error);

  await renderDetailPage();
  await submitApprove(user);
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
    await renderWithRequests(buildRequest('pending_review'));

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

    await renderWithRequests(buildRequest('pending_review'), buildRequest('under_repair'));
    await submitApprove(user);

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

    await renderWithRequests(buildRequest('pending_review'), buildRequest('under_repair'));
    await submitApprove(user, approveFields.withoutCost);

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

    await renderWithRequests(buildRequest('pending_review'), buildRequest('under_repair'));
    await submitApprove(user, approveFields.empty);

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith('rr-1', {
        version: 1,
      });
    });
  });

  it('moves reject operation to review details page and submits payload', async () => {
    const user = userEvent.setup({ delay: null });

    await renderWithRequests(buildRequest('pending_review'), buildRequest('rejected'));
    await waitForAction('Reject');
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

    await renderWithRequests(
      buildRequest('under_repair'),
      buildRequest('under_repair'),
      buildRequest('completed'),
    );
    await waitForAction('Update Details');
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

    await submitComplete(user, completedRepairDetails);

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

    await renderWithRequests(buildRequest('under_repair'), buildRequest('under_repair'));
    await waitForAction('Update Details');
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

    await renderWithRequests(buildRequest('under_repair'));
    await waitForAction('Update Details');
    await clickButton(user, 'Update Details');
    await clickButton(user, 'Save');

    await waitFor(() => {
      expect(screen.getByText('Enter at least one repair detail')).toBeInTheDocument();
    });
    expect(mockUpdateRepairRequestDetails).not.toHaveBeenCalled();
  });

  it('omits a blank optional repair cost when updating existing repair details', async () => {
    const user = userEvent.setup({ delay: null });

    await renderWithRequests(buildUnderRepairWithDetails(), buildUnderRepairWithDetails());
    await waitForAction('Update Details');
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

    await renderWithRequests(request);

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
    mockApproveRepairRequest.mockRejectedValueOnce(
      new apiModule.ApiError(409, 'conflict', 'Conflict occurred'),
    );

    await renderWithRequests(buildRequest('pending_review'), buildRequest('pending_review'));
    await submitApprove(user);

    await waitFor(() => {
      expect(screen.getAllByText('Update Conflict')[0]).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'OK' }));
    });

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

    await renderWithRequests(buildRequest('under_repair'), buildRequest('completed'));
    await submitComplete(user, zeroCostCompletedRepairDetails);

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
