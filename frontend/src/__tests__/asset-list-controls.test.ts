import { describe, expect, it } from 'vitest';

import type { AssetRecord } from '@/api/assets';
import {
  applyLocalAssetFilters,
  applyLocalAssetSort,
  buildServerSortParam,
  buildBaseServerParams,
  isAssetFilterField,
  isAssetSortField,
  isServerSortableField,
  normalizeFilters,
  normalizeAssetCategoryLiteral,
  paginateAssets,
  shouldUseClientGlobalMode,
  type AssetListFilters,
  type AssetSortField,
} from '@/components/assets/listControls';

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
    activation_date: '2026-01-05',
    warranty_expiry: '2028-01-01',
    assignment_date: '2026-01-10',
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

const DEFAULT_FILTERS: AssetListFilters = {
  q: '',
  category: undefined,
  department: '',
  location: '',
  holder: '',
};

describe('asset list controls', () => {
  const assets: AssetRecord[] = [
    buildAsset({
      id: 'asset-1',
      asset_code: 'AST-2026-00003',
      name: 'Gamma Workstation',
      category: 'computer',
      department: 'Engineering',
      location: 'Taipei HQ 3F',
      purchase_amount: '300.00',
      purchase_date: '2026-03-01',
      status: 'in_use',
    }),
    buildAsset({
      id: 'asset-2',
      asset_code: 'AST-2026-00001',
      name: 'Alpha Printer',
      category: 'printer',
      department: 'Finance',
      location: 'Taichung Branch 2F',
      purchase_amount: '100.00',
      purchase_date: 'not-a-date',
      status: 'in_stock',
      responsible_person_id: 'holder-2',
      responsible_person: {
        id: 'holder-2',
        name: 'Bob Lee',
        department: 'Operations',
        location: 'Taichung Branch 2F',
      },
    }),
    buildAsset({
      id: 'asset-3',
      asset_code: 'AST-2026-00002',
      name: 'beta phone',
      category: 'assetList.category.Phone',
      department: 'Operations',
      location: 'Tainan Lab 1F',
      purchase_amount: 'not-a-number',
      purchase_date: '',
      status: 'disposed',
      responsible_person_id: 'holder-fallback-3',
      responsible_person: null,
    }),
  ];

  it('validates sort/filter field guards', () => {
    expect(isAssetSortField('asset_code')).toBe(true);
    expect(isAssetSortField('invalid_field')).toBe(false);
    expect(isAssetSortField(123)).toBe(false);

    expect(isAssetFilterField('department')).toBe(true);
    expect(isAssetFilterField('category')).toBe(true);
    expect(isAssetFilterField(null)).toBe(false);
  });

  it('validates server sortable field guard', () => {
    expect(isServerSortableField('asset_code')).toBe(true);
    expect(isServerSortableField('purchase_date')).toBe(true);
    expect(isServerSortableField('purchase_amount')).toBe(false);
  });

  it('normalizes category literals for known and unknown values', () => {
    expect(normalizeAssetCategoryLiteral('assetList.category.Phone')).toBe('phone');
    expect(normalizeAssetCategoryLiteral('Network Equipment')).toBe('network_equipment');
    expect(normalizeAssetCategoryLiteral('LegacyCustomType')).toBe('LegacyCustomType');
  });

  it('normalizes filters and builds server params/sort params', () => {
    const normalized = normalizeFilters({
      q: '  AST  ',
      status: 'in_stock',
      category: 'computer',
      department: '  Engineering  ',
      location: '  HQ  ',
      holder: '  alice  ',
    });

    expect(normalized).toEqual({
      q: 'AST',
      status: 'in_stock',
      category: 'computer',
      department: 'Engineering',
      location: 'HQ',
      holder: 'alice',
    });

    expect(
      buildBaseServerParams({
        ...DEFAULT_FILTERS,
        q: '',
      }),
    ).toEqual({ q: undefined, status: undefined, category: undefined });

    expect(buildServerSortParam(null)).toBeUndefined();
    expect(buildServerSortParam({ field: 'purchase_amount', order: 'ascend' })).toBeUndefined();
    expect(buildServerSortParam({ field: 'asset_code', order: 'ascend' })).toBe('asset_code');
    expect(buildServerSortParam({ field: 'status', order: 'descend' })).toBe('-status');
  });

  it('switches to client global mode only when needed', () => {
    expect(
      shouldUseClientGlobalMode(
        {
          ...DEFAULT_FILTERS,
          department: 'engi',
        },
        null,
      ),
    ).toBe(true);

    expect(
      shouldUseClientGlobalMode(
        {
          ...DEFAULT_FILTERS,
        },
        { field: 'purchase_amount', order: 'descend' },
      ),
    ).toBe(true);

    expect(
      shouldUseClientGlobalMode(
        {
          ...DEFAULT_FILTERS,
        },
        { field: 'asset_code', order: 'ascend' },
      ),
    ).toBe(false);

    expect(
      shouldUseClientGlobalMode(
        {
          ...DEFAULT_FILTERS,
        },
        null,
      ),
    ).toBe(false);
  });

  it('applies q/status/category/department/location filters', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      q: 'alpha',
      status: 'in_stock',
      category: 'printer',
      department: 'fin',
      location: 'branch',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.asset_code).toBe('AST-2026-00001');
  });

  it('excludes assets when status does not match', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      status: 'under_repair',
    });

    expect(filtered).toHaveLength(0);
  });

  it('excludes assets when category enum does not match exactly', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      category: 'monitor',
    });

    expect(filtered).toHaveLength(0);
  });

  it('excludes assets when department substring does not match', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      department: 'legal',
    });

    expect(filtered).toHaveLength(0);
  });

  it('excludes assets when location substring does not match', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      location: 'kaohsiung',
    });

    expect(filtered).toHaveLength(0);
  });

  it('applies holder substring filter on responsible person name', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      holder: 'bob',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.asset_code).toBe('AST-2026-00001');
  });

  it('applies holder substring filter on responsible person id fallback', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      holder: 'fallback-3',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.asset_code).toBe('AST-2026-00002');
  });

  it('returns original reference when no local sort state is provided', () => {
    const sorted = applyLocalAssetSort(assets, null);
    expect(sorted).toBe(assets);
  });

  it('applies local sorting for every supported sort field', () => {
    const expectedFirstByField: Record<AssetSortField, string> = {
      asset_code: 'asset-2',
      name: 'asset-2',
      category: 'asset-1',
      department: 'asset-1',
      location: 'asset-2',
      status: 'asset-3',
      purchase_amount: 'asset-3',
      purchase_date: 'asset-2',
    };

    for (const [field, expectedFirstId] of Object.entries(expectedFirstByField) as Array<
      [AssetSortField, string]
    >) {
      const sorted = applyLocalAssetSort(assets, {
        field,
        order: 'ascend',
      });

      expect(sorted[0]?.id).toBe(expectedFirstId);
    }

    const descSorted = applyLocalAssetSort(assets, {
      field: 'asset_code',
      order: 'descend',
    });

    expect(descSorted[0]?.id).toBe('asset-1');
  });

  it('keeps stable order when sort field falls through default branch', () => {
    const sorted = applyLocalAssetSort(assets, {
      field: 'unsupported' as AssetSortField,
      order: 'ascend',
    });

    expect(sorted.map((asset) => asset.id)).toEqual(assets.map((asset) => asset.id));
  });

  it('paginates local assets with page/perPage', () => {
    const paged = paginateAssets(assets, 2, 2);
    expect(paged).toHaveLength(1);
    expect(paged[0]?.id).toBe('asset-3');
  });

  it('returns empty array when filters do not match', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      q: 'does-not-exist',
    });

    expect(filtered).toHaveLength(0);
  });
});
