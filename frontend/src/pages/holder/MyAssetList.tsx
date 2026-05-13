import React, { useCallback } from 'react';
import { assetsApi } from '../../api';
import { useAssetList } from '../../hooks/useAssetList';
import AssetListContainer from '../../components/assets/AssetListContainer';

const MyAssetList: React.FC = () => {
  const fetchFn = useCallback(
    (params: { page: number; perPage: number }) => assetsApi.listMyAssets(params),
    [],
  );

  const {
    assets,
    total,
    loading,
    error,
    page,
    pageSize,
    setPage,
    setPageSize,
  } = useAssetList({ fetchFn });

  return (
    <AssetListContainer
      assets={assets}
      loading={loading}
      total={total}
      error={error}
      page={page}
      pageSize={pageSize}
      onPaginationChange={(nextPage, nextPageSize) => {
        setPage(nextPage);
        setPageSize(nextPageSize);
      }}
    />
  );
};

export default MyAssetList;
