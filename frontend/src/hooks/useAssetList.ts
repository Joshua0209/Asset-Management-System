import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api';
import type { AssetRecord, ListAssetsParams } from '@/api/assets';
import { PAGE_SIZE_OPTIONS } from '@/components/assets/constants';
import {
  applyLocalAssetFilters,
  applyLocalAssetSort,
  buildBaseServerParams,
  buildServerSortParam,
  DEFAULT_ASSET_LIST_FILTERS,
  normalizeFilters,
  paginateAssets,
  shouldUseClientGlobalMode,
  type AssetListFilters,
  type AssetSortState,
} from '@/components/assets/listControls';

const GLOBAL_MODE_PER_PAGE = 100;
const SEARCH_DEBOUNCE_MS = 300;

interface UseAssetListOptions {
  fetchFn: (params: ListAssetsParams) => Promise<{
    data: AssetRecord[];
    meta: { total: number; total_pages?: number };
  }>;
  enabled?: boolean;
}

async function fetchAllAssets(
  fetchFn: UseAssetListOptions['fetchFn'],
  baseParams: Omit<ListAssetsParams, 'page' | 'perPage' | 'sort'>,
): Promise<AssetRecord[]> {
  const firstPage = await fetchFn({
    ...baseParams,
    page: 1,
    perPage: GLOBAL_MODE_PER_PAGE,
  });

  const totalPages =
    firstPage.meta.total_pages ?? Math.ceil(firstPage.meta.total / GLOBAL_MODE_PER_PAGE);

  if (totalPages <= 1) {
    return firstPage.data;
  }

  const remainingRequests: Array<ReturnType<UseAssetListOptions['fetchFn']>> = [];

  for (let currentPage = 2; currentPage <= totalPages; currentPage += 1) {
    remainingRequests.push(
      fetchFn({
        ...baseParams,
        page: currentPage,
        perPage: GLOBAL_MODE_PER_PAGE,
      }),
    );
  }

  const remainingPages = await Promise.all(remainingRequests);

  return [firstPage, ...remainingPages].flatMap((response) => response.data);
}

export const useAssetList = ({ fetchFn, enabled = true }: UseAssetListOptions) => {
  const { t } = useTranslation();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [filters, setFilters] = useState<AssetListFilters>({
    ...DEFAULT_ASSET_LIST_FILTERS,
  });
  const [sortState, setSortState] = useState<AssetSortState | null>(null);
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const timeoutId = globalThis.setTimeout(() => {
      setDebouncedKeyword(filters.q);
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      globalThis.clearTimeout(timeoutId);
    };
  }, [filters.q]);

  const normalizedFilters = useMemo(
    () =>
      normalizeFilters({
        q: debouncedKeyword,
        status: filters.status,
        category: filters.category,
        department: filters.department,
        location: filters.location,
        holder: filters.holder,
      }),
    [
      debouncedKeyword,
      filters.category,
      filters.department,
      filters.holder,
      filters.location,
      filters.status,
    ],
  );

  const useClientGlobalMode = useMemo(
    () => shouldUseClientGlobalMode(normalizedFilters, sortState),
    [normalizedFilters, sortState],
  );

  useEffect(() => {
    if (!enabled) {
      setAssets([]);
      setTotal(0);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);

      try {
        const baseServerParams = buildBaseServerParams(normalizedFilters);

        if (useClientGlobalMode) {
          const allAssets = await fetchAllAssets(fetchFn, baseServerParams);
          if (cancelled) {
            return;
          }

          const locallyFiltered = applyLocalAssetFilters(allAssets, normalizedFilters);
          const locallySorted = applyLocalAssetSort(locallyFiltered, sortState);

          setAssets(paginateAssets(locallySorted, page, pageSize));
          setTotal(locallySorted.length);
        } else {
          const response = await fetchFn({
            ...baseServerParams,
            page,
            perPage: pageSize,
            sort: buildServerSortParam(sortState),
          });
          if (cancelled) {
            return;
          }
          setAssets(response.data);
          setTotal(response.meta.total);
        }
      } catch (e) {
        if (cancelled) {
          return;
        }

        setAssets([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, [
    fetchFn,
    enabled,
    normalizedFilters,
    page,
    pageSize,
    reloadToken,
    sortState,
    t,
    useClientGlobalMode,
  ]);

  const onFilterChange = useCallback(
    <K extends keyof AssetListFilters>(field: K, value: AssetListFilters[K]) => {
      setPage(1);
      setFilters((previous) => ({
        ...previous,
        [field]: value,
      }));
    },
    [],
  );

  const onResetFilters = useCallback(() => {
    setPage(1);
    setFilters({ ...DEFAULT_ASSET_LIST_FILTERS });
    setDebouncedKeyword('');
  }, []);

  const onSortChange = useCallback((nextSortState: AssetSortState | null) => {
    setPage(1);
    setSortState(nextSortState);
  }, []);

  const resetQueryState = useCallback(() => {
    setPage(1);
    setFilters({ ...DEFAULT_ASSET_LIST_FILTERS });
    setSortState(null);
    setDebouncedKeyword('');
  }, []);

  const reload = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  return {
    assets,
    total,
    loading,
    error,
    page,
    pageSize,
    setPage,
    setPageSize,
    filters,
    onFilterChange,
    onResetFilters,
    sortState,
    onSortChange,
    resetQueryState,
    reload,
  };
};
