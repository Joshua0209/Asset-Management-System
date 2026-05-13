import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api';
import type { AssetRecord } from '@/api/assets';
import { PAGE_SIZE_OPTIONS } from '@/components/assets/constants';

interface UseAssetListOptions {
  fetchFn: (params: { page: number; perPage: number }) => Promise<{
    data: AssetRecord[];
    meta: { total: number };
  }>;
}

export const useAssetList = ({ fetchFn }: UseAssetListOptions) => {
  const { t } = useTranslation();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);

  useEffect(() => {
    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchFn({ page, perPage: pageSize });
        if (cancelled) return;
        setAssets(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) return;
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
  }, [page, pageSize, t, fetchFn]);

  return {
    assets,
    total,
    loading,
    error,
    page,
    pageSize,
    setPage,
    setPageSize,
  };
};
