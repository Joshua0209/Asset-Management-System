import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AssetRecord } from '@/api/assets';
import type { AssetSortState } from '@/components/assets/listControls';
import AssetTable from '@/components/assets/AssetTable';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      typeof options?.count === 'number' ? `${key}:${options.count}` : key,
  }),
}));

type MockSortPayload =
  | {
      columnKey?: string;
      order?: 'ascend' | 'descend' | null;
    }
  | Array<{
      columnKey?: string;
      order?: 'ascend' | 'descend' | null;
    }>;

interface MockTableProps {
  dataSource: AssetRecord[];
  columns: Array<{
    key?: string;
    render?: (_value: unknown, asset: AssetRecord) => React.ReactNode;
  }>;
  onChange?: (_pagination: unknown, _filters: unknown, sorter: MockSortPayload) => void;
  pagination?: {
    onChange?: (page: number, pageSize: number) => void;
  };
}

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');

  const Button = ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  );

  const Table = ({ dataSource, columns, onChange, pagination }: MockTableProps) => {
    const actionsColumn = columns.find((column: { key?: string }) => column.key === 'actions');

    return (
      <div>
        <button
          type="button"
          onClick={() => onChange?.({}, {}, { columnKey: 'name', order: 'ascend' })}
        >
          emit-sort-name-asc
        </button>
        <button
          type="button"
          onClick={() => onChange?.({}, {}, [{ columnKey: 'purchase_amount', order: 'descend' }])}
        >
          emit-sort-array-desc
        </button>
        <button
          type="button"
          onClick={() => onChange?.({}, {}, { columnKey: 'unknown', order: 'ascend' })}
        >
          emit-sort-invalid
        </button>
        <button
          type="button"
          onClick={() => onChange?.({}, {}, { columnKey: 'name', order: null })}
        >
          emit-sort-clear
        </button>
        <button type="button" onClick={() => pagination?.onChange?.(2, 10)}>
          emit-page-2
        </button>

        {actionsColumn
          ? dataSource.map((asset: AssetRecord) => (
              <div key={asset.id}>{actionsColumn.render?.(undefined, asset)}</div>
            ))
          : null}
      </div>
    );
  };

  return {
    ...actual,
    Button,
    Table,
  };
});

function buildAsset(id: string, code: string, name: string): AssetRecord {
  return {
    id,
    asset_code: code,
    name,
    model: 'Model-X',
    specs: null,
    category: 'computer',
    supplier: 'Vendor',
    purchase_date: '2026-01-01',
    purchase_amount: '1000.00',
    location: 'Taipei HQ',
    department: 'IT',
    activation_date: null,
    warranty_expiry: null,
    assignment_date: null,
    unassignment_date: null,
    status: 'in_stock',
    responsible_person_id: null,
    responsible_person: null,
    disposal_reason: null,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function renderTable(sortState: AssetSortState | null = null) {
  const onPaginationChange = vi.fn();
  const onSortChange = vi.fn();

  render(
    <AssetTable
      assets={[buildAsset('asset-1', 'AST-2026-00001', 'Business Laptop')]}
      loading={false}
      total={1}
      page={1}
      pageSize={5}
      sortState={sortState}
      onPaginationChange={onPaginationChange}
      onSortChange={onSortChange}
    />,
  );

  return {
    onPaginationChange,
    onSortChange,
  };
}

describe('AssetTable', () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  it('navigates to asset detail page from actions column', async () => {
    renderTable();
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole('button', { name: 'assetList.actions.detail' }));

    expect(mockNavigate).toHaveBeenCalledWith('/assets/asset-1');
  });

  it('forwards pagination changes', async () => {
    const { onPaginationChange } = renderTable();
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole('button', { name: 'emit-page-2' }));

    expect(onPaginationChange).toHaveBeenCalledWith(2, 10);
  });

  it('emits sort changes for object and array sorter payloads', async () => {
    const { onSortChange } = renderTable();
    const user = userEvent.setup({ delay: null });

    await user.click(screen.getByRole('button', { name: 'emit-sort-name-asc' }));
    await user.click(screen.getByRole('button', { name: 'emit-sort-array-desc' }));

    expect(onSortChange).toHaveBeenNthCalledWith(1, {
      field: 'name',
      order: 'ascend',
    });
    expect(onSortChange).toHaveBeenNthCalledWith(2, {
      field: 'purchase_amount',
      order: 'descend',
    });
  });

  it('ignores invalid/unchanged sort but emits when clearing active sort', async () => {
    const user = userEvent.setup({ delay: null });

    const first = renderTable();
    await user.click(screen.getByRole('button', { name: 'emit-sort-invalid' }));
    expect(first.onSortChange).not.toHaveBeenCalled();

    const second = renderTable({ field: 'name', order: 'ascend' });
    await user.click(screen.getAllByRole('button', { name: 'emit-sort-name-asc' })[1]);
    expect(second.onSortChange).not.toHaveBeenCalled();

    await user.click(screen.getAllByRole('button', { name: 'emit-sort-clear' })[1]);
    expect(second.onSortChange).toHaveBeenCalledWith(null);
  });
});
