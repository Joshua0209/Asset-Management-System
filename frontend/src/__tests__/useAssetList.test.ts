import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/api';
import type { AssetRecord, ListAssetsParams } from '@/api/assets';
import { PAGE_SIZE_OPTIONS } from '@/components/assets/constants';
import { DEFAULT_ASSET_LIST_FILTERS } from '@/components/assets/listControls';
import { useAssetList } from '@/hooks/useAssetList';

const translate = (key: string) => key;

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: translate,
    }),
  };
});

function buildAsset(overrides: Partial<AssetRecord>): AssetRecord {
  return {
    id: 'asset-1',
    asset_code: 'AST-2026-00001',
    name: 'Business Laptop 13',
    model: 'Model-A',
    specs: null,
    category: 'computer',
    supplier: 'Vendor A',
    purchase_date: '2026-01-01',
    purchase_amount: '42900.00',
    location: 'Taipei HQ 3F',
    department: 'Engineering',
    activation_date: null,
    warranty_expiry: null,
    assignment_date: null,
    unassignment_date: null,
    status: 'in_use',
    responsible_person_id: 'holder-1',
    responsible_person: {
      id: 'holder-1',
      name: 'Alice Chen',
      department: 'Engineering',
      location: 'Taipei HQ 3F',
    },
    disposal_reason: null,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

type FetchResponse = {
  data: AssetRecord[];
  meta: { total: number; total_pages?: number };
};

type FetchFn = (params: ListAssetsParams) => Promise<FetchResponse>;

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return {
    promise,
    resolve,
    reject,
  };
}

const DEFAULT_PER_PAGE = PAGE_SIZE_OPTIONS[0];

async function renderAndWaitForInitialLoad(fetchFn: ReturnType<typeof vi.fn<FetchFn>>) {
  const rendered = renderHook(() => useAssetList({ fetchFn }));

  await waitFor(() => {
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  return rendered;
}

describe('useAssetList', () => {
  it('does not fetch data when disabled', () => {
    const fetchFn = vi.fn<FetchFn>();

    const { result } = renderHook(() => useAssetList({ fetchFn, enabled: false }));

    expect(fetchFn).not.toHaveBeenCalled();
    expect(result.current.assets).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('loads in server mode and sends server-sortable sort param', async () => {
    const fetchFn = vi.fn<FetchFn>().mockResolvedValue({
      data: [buildAsset({ id: 'asset-server' })],
      meta: { total: 1, total_pages: 1 },
    });

    const { result } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledWith({
        q: undefined,
        status: undefined,
        category: undefined,
        page: 1,
        perPage: DEFAULT_PER_PAGE,
        sort: undefined,
      });
    });

    act(() => {
      result.current.onSortChange({ field: 'asset_code', order: 'descend' });
    });

    await waitFor(() => {
      expect(fetchFn).toHaveBeenLastCalledWith({
        q: undefined,
        status: undefined,
        category: undefined,
        page: 1,
        perPage: DEFAULT_PER_PAGE,
        sort: '-asset_code',
      });
    });
  });

  it('forwards exact category enum filter in server mode', async () => {
    const fetchFn = vi.fn<FetchFn>().mockResolvedValue({
      data: [buildAsset({ id: 'asset-category' })],
      meta: { total: 1, total_pages: 1 },
    });

    const { result } = await renderAndWaitForInitialLoad(fetchFn);

    act(() => {
      result.current.onFilterChange('category', 'computer');
    });

    await waitFor(() => {
      expect(fetchFn).toHaveBeenLastCalledWith({
        q: undefined,
        status: undefined,
        category: 'computer',
        page: 1,
        perPage: DEFAULT_PER_PAGE,
        sort: undefined,
      });
    });
  });

  it('switches to client-global mode for substring filters and local client-only sorting', async () => {
    const engineeringLowAmount = buildAsset({
      id: 'asset-eng-low',
      department: 'Engineering',
      purchase_amount: '100.00',
    });
    const engineeringHighAmount = buildAsset({
      id: 'asset-eng-high',
      department: 'Engineering',
      purchase_amount: '500.00',
      asset_code: 'AST-2026-00002',
      name: 'Business Laptop 15',
    });

    const fetchFn = vi.fn<FetchFn>(async (params) => {
      if (params.perPage === 100 && params.page === 1) {
        return {
          data: [engineeringLowAmount],
          meta: { total: 2, total_pages: 2 },
        };
      }
      if (params.perPage === 100 && params.page === 2) {
        return {
          data: [engineeringHighAmount],
          meta: { total: 2, total_pages: 2 },
        };
      }

      return {
        data: [engineeringLowAmount, engineeringHighAmount],
        meta: { total: 2, total_pages: 1 },
      };
    });

    const { result } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledTimes(1);
    });

    act(() => {
      result.current.onFilterChange('department', 'eng');
    });

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledWith({
        q: undefined,
        status: undefined,
        category: undefined,
        page: 1,
        perPage: 100,
      });
      expect(fetchFn).toHaveBeenCalledWith({
        q: undefined,
        status: undefined,
        category: undefined,
        page: 2,
        perPage: 100,
      });
    });

    await waitFor(() => {
      expect(result.current.total).toBe(2);
      expect(result.current.assets.map((asset) => asset.id)).toEqual([
        'asset-eng-low',
        'asset-eng-high',
      ]);
    });

    act(() => {
      result.current.onSortChange({ field: 'purchase_amount', order: 'descend' });
    });

    await waitFor(() => {
      expect(result.current.assets[0]?.id).toBe('asset-eng-high');
    });
  });

  it('uses only first global page when client mode total pages is one', async () => {
    const onlyAsset = buildAsset({
      id: 'asset-single-page-client',
      department: 'Engineering',
    });

    const fetchFn = vi.fn<FetchFn>().mockResolvedValue({
      data: [onlyAsset],
      meta: { total: 1, total_pages: 1 },
    });

    const { result } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledTimes(1);
    });

    act(() => {
      result.current.onFilterChange('department', 'eng');
    });

    await waitFor(() => {
      const globalCalls = fetchFn.mock.calls.filter(([params]) => params.perPage === 100);
      expect(globalCalls).toHaveLength(1);
      expect(result.current.total).toBe(1);
      expect(result.current.assets[0]?.id).toBe('asset-single-page-client');
    });
  });

  it('debounces q filter and supports reset/reload APIs', async () => {
    const fetchFn = vi.fn<FetchFn>().mockResolvedValue({
      data: [buildAsset({ id: 'asset-debounce' })],
      meta: { total: 1, total_pages: 1 },
    });

    const { result } = await renderAndWaitForInitialLoad(fetchFn);

    act(() => {
      result.current.onFilterChange('q', 'Laptop');
    });

    expect(result.current.filters.q).toBe('Laptop');
    expect(fetchFn).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledTimes(2);
      expect(fetchFn).toHaveBeenLastCalledWith({
        q: 'Laptop',
        status: undefined,
        category: undefined,
        page: 1,
        perPage: DEFAULT_PER_PAGE,
        sort: undefined,
      });
    });

    act(() => {
      result.current.setPage(2);
      result.current.onSortChange({ field: 'name', order: 'ascend' });
      result.current.onResetFilters();
    });

    expect(result.current.page).toBe(1);
    expect(result.current.filters).toEqual(DEFAULT_ASSET_LIST_FILTERS);

    act(() => {
      result.current.resetQueryState();
    });

    expect(result.current.page).toBe(1);
    expect(result.current.sortState).toBeNull();
    expect(result.current.filters).toEqual(DEFAULT_ASSET_LIST_FILTERS);

    const fetchCallCountBeforeReload = fetchFn.mock.calls.length;
    act(() => {
      result.current.reload();
    });

    await waitFor(() => {
      expect(fetchFn.mock.calls.length).toBeGreaterThan(fetchCallCountBeforeReload);
    });
  });

  it('exposes ApiError message and clears data on API failure', async () => {
    const fetchFn = vi.fn<FetchFn>().mockRejectedValue(new ApiError(400, 'bad_request', 'bad request'));

    const { result } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(result.current.error).toBe('bad request');
    });

    expect(result.current.assets).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.loading).toBe(false);
  });

  it('falls back to translated generic server error for unknown errors', async () => {
    const fetchFn = vi.fn<FetchFn>().mockRejectedValue(new Error('unexpected'));

    const { result } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(result.current.error).toBe('assetList.serverError');
    });
  });

  it('ignores late successful responses after unmount', async () => {
    const deferred = createDeferred<FetchResponse>();
    const fetchFn = vi.fn<FetchFn>().mockReturnValue(deferred.promise);

    const { unmount } = renderHook(() => useAssetList({ fetchFn }));

    expect(fetchFn).toHaveBeenCalledTimes(1);
    unmount();

    await act(async () => {
      deferred.resolve({
        data: [buildAsset({ id: 'asset-late-success' })],
        meta: { total: 1, total_pages: 1 },
      });
      await Promise.resolve();
    });

    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it('ignores late failed responses after unmount', async () => {
    const deferred = createDeferred<FetchResponse>();
    const fetchFn = vi.fn<FetchFn>().mockReturnValue(deferred.promise);

    const { unmount } = renderHook(() => useAssetList({ fetchFn }));

    expect(fetchFn).toHaveBeenCalledTimes(1);
    unmount();

    await act(async () => {
      deferred.reject(new Error('late failure'));
      await Promise.resolve();
    });

    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it('ignores late client-mode responses after unmount', async () => {
    const deferred = createDeferred<FetchResponse>();
    const initialAsset = buildAsset({ id: 'asset-initial' });

    const fetchFn = vi.fn<FetchFn>(async (params) => {
      if (params.perPage === 100) {
        return deferred.promise;
      }

      return {
        data: [initialAsset],
        meta: { total: 1, total_pages: 1 },
      };
    });

    const { result, unmount } = renderHook(() => useAssetList({ fetchFn }));

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledTimes(1);
    });

    act(() => {
      result.current.onFilterChange('department', 'eng');
    });

    await waitFor(() => {
      expect(fetchFn).toHaveBeenCalledWith({
        q: undefined,
        status: undefined,
        category: undefined,
        page: 1,
        perPage: 100,
      });
    });

    unmount();

    await act(async () => {
      deferred.resolve({
        data: [buildAsset({ id: 'asset-late-client' })],
        meta: { total: 1, total_pages: 1 },
      });
      await Promise.resolve();
    });

    expect(fetchFn).toHaveBeenCalledTimes(2);
  });
});
