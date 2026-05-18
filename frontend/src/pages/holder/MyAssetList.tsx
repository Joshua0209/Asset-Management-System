import React, { useCallback } from 'react';
import { assetsApi } from '@/api';
import type { ListAssetsParams } from '@/api/assets';
import { useAssetList } from '@/hooks/useAssetList';
import AssetListContainer from '@/components/assets/AssetListContainer';

const MyAssetList: React.FC = () => {
  const fetchFn = useCallback((params: ListAssetsParams) => assetsApi.listMyAssets(params), []);

  const {
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
  } = useAssetList({ fetchFn });

  return (
    <AssetListContainer
      assets={assets}
      loading={loading}
      total={total}
      error={error}
      page={page}
      pageSize={pageSize}
      filters={filters}
      sortState={sortState}
      isManager={false}
      onFilterChange={onFilterChange}
      onResetFilters={onResetFilters}
      onPaginationChange={(nextPage, nextPageSize) => {
        setPage(nextPage);
        setPageSize(nextPageSize);
      }}
      onSortChange={onSortChange}
    />
  );
};

export default MyAssetList;
