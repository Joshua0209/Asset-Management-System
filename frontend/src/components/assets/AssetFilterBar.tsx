import React from 'react';
import { Button, Input, Select, Space } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AssetStatus } from '@/api/assets';
import type { AssetListFilters } from './listControls';

interface AssetFilterBarProps {
  filters: AssetListFilters;
  isManager: boolean;
  onFilterChange: <K extends keyof AssetListFilters>(
    field: K,
    value: AssetListFilters[K],
  ) => void;
  onResetFilters: () => void;
}

const STATUS_OPTIONS: AssetStatus[] = [
  'in_stock',
  'in_use',
  'pending_repair',
  'under_repair',
  'disposed',
];

const AssetFilterBar: React.FC<AssetFilterBarProps> = ({
  filters,
  isManager,
  onFilterChange,
  onResetFilters,
}) => {
  const { t } = useTranslation();

  return (
    <Space size={8} wrap>
      <Input
        allowClear
        value={filters.q}
        style={{ width: 240 }}
        placeholder={t('assetList.filters.searchPlaceholder')}
        onChange={(event) => onFilterChange('q', event.target.value)}
      />

      <Select
        allowClear
        value={filters.status}
        style={{ width: 180 }}
        placeholder={t('assetList.filters.statusPlaceholder')}
        options={STATUS_OPTIONS.map((status) => ({
          value: status,
          label: t(`assetList.status.${status}`),
        }))}
        onChange={(value) => onFilterChange('status', value)}
      />

      <Input
        allowClear
        value={filters.department}
        style={{ width: 200 }}
        placeholder={t('assetList.filters.departmentPlaceholder')}
        onChange={(event) => onFilterChange('department', event.target.value)}
      />

      <Input
        allowClear
        value={filters.location}
        style={{ width: 200 }}
        placeholder={t('assetList.filters.locationPlaceholder')}
        onChange={(event) => onFilterChange('location', event.target.value)}
      />

      {isManager ? (
        <Input
          allowClear
          value={filters.holder}
          style={{ width: 220 }}
          placeholder={t('assetList.filters.holderPlaceholder')}
          onChange={(event) => onFilterChange('holder', event.target.value)}
        />
      ) : null}

      <Button onClick={onResetFilters}>{t('assetList.filters.resetButton')}</Button>
    </Space>
  );
};

export default AssetFilterBar;
