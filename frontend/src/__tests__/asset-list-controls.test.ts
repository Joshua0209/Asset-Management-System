import { describe, expect, it } from 'vitest';

import type { AssetRecord } from '@/api/assets';
import {
  applyLocalAssetFilters,
  buildBaseServerParams,
  normalizeAssetCategoryLiteral,
  shouldUseClientGlobalMode,
  type AssetListFilters,
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
    responsible_person: { id: 'holder-1', name: 'Alice Chen' },
    disposal_reason: null,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const DEFAULT_FILTERS: AssetListFilters = {
  q: '',
  department: '',
  location: '',
  holder: '',
};

describe('asset list controls', () => {
  const assets: AssetRecord[] = [
    buildAsset({
      id: 'asset-1',
      asset_code: 'AST-2026-00001',
      category: 'computer',
      department: 'Engineering',
      location: 'Taipei HQ 3F',
    }),
    buildAsset({
      id: 'asset-2',
      asset_code: 'AST-2026-00002',
      category: 'printer',
      department: 'Finance',
      location: 'Taichung Branch 2F',
      responsible_person_id: 'holder-2',
      responsible_person: { id: 'holder-2', name: 'Bob Lee' },
    }),
    buildAsset({
      id: 'asset-3',
      asset_code: 'AST-2026-00003',
      category: 'tablet',
      department: 'Operations',
      location: 'Tainan Lab 1F',
      status: 'in_stock',
      responsible_person_id: null,
      responsible_person: null,
    }),
  ];

  it('applies department/location as substring filters', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      department: 'engi',
      location: 'hq',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.asset_code).toBe('AST-2026-00001');
  });

  it('keeps department/location out of server base params', () => {
    const serverParams = buildBaseServerParams({
      ...DEFAULT_FILTERS,
      q: 'AST',
      department: 'Engineering',
      location: 'Taipei',
      holder: 'alice',
    });

    expect(serverParams).toEqual({
      q: 'AST',
      status: undefined,
    });
  });

  it('switches to client global mode when substring filter is present', () => {
    const clientMode = shouldUseClientGlobalMode(
      {
        ...DEFAULT_FILTERS,
        department: 'eng',
      },
      null,
    );

    expect(clientMode).toBe(true);
  });

  it('applies holder substring filter on responsible person name', () => {
    const filtered = applyLocalAssetFilters(assets, {
      ...DEFAULT_FILTERS,
      holder: 'bob',
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.asset_code).toBe('AST-2026-00002');
  });

  it('normalizes prefixed and cased category literal utility output', () => {
    expect(normalizeAssetCategoryLiteral('assetList.category.Phone')).toBe('phone');
  });
});
