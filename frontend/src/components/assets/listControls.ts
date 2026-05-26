import type {
  AssetCategory,
  AssetRecord,
  AssetStatus,
  ListAssetsParams,
} from '@/api/assets';

export type AssetSortField =
  | 'asset_code'
  | 'name'
  | 'category'
  | 'department'
  | 'location'
  | 'status'
  | 'purchase_amount'
  | 'purchase_date';

export type AssetSortOrder = 'ascend' | 'descend';

export interface AssetSortState {
  field: AssetSortField;
  order: AssetSortOrder;
}

export interface AssetListFilters {
  q: string;
  status?: AssetStatus;
  category?: AssetCategory;
  department: string;
  location: string;
  holder: string;
}

export const DEFAULT_ASSET_LIST_FILTERS: AssetListFilters = {
  q: '',
  department: '',
  location: '',
  holder: '',
};

const SERVER_SORTABLE_FIELDS = new Set<AssetSortField>([
  'asset_code',
  'name',
  'status',
  'purchase_date',
]);

const CLIENT_ONLY_SORTABLE_FIELDS = new Set<AssetSortField>([
  'category',
  'department',
  'location',
  'purchase_amount',
]);

const FILTERABLE_FIELDS = new Set<keyof AssetListFilters>([
  'q',
  'status',
  'category',
  'department',
  'location',
  'holder',
]);

const CATEGORY_I18N_PREFIX = 'assetList.category.';
const KNOWN_CATEGORY_VALUES = new Set<AssetCategory>([
  'phone',
  'computer',
  'tablet',
  'monitor',
  'printer',
  'network_equipment',
  'other',
]);

function toLowerText(value: string | null | undefined): string {
  return (value ?? '').toLowerCase();
}

function toAmountNumber(value: string | number | null | undefined): number {
  const parsed = Number.parseFloat(String(value ?? ''));
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function toDateTimestamp(value: string | null | undefined): number {
  if (!value) {
    return Number.NEGATIVE_INFINITY;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
}

function compareStrings(left: string, right: string): number {
  return left.localeCompare(right);
}

function compareByField(left: AssetRecord, right: AssetRecord, field: AssetSortField): number {
  switch (field) {
    case 'purchase_amount': {
      return toAmountNumber(left.purchase_amount) - toAmountNumber(right.purchase_amount);
    }
    case 'purchase_date': {
      return toDateTimestamp(left.purchase_date) - toDateTimestamp(right.purchase_date);
    }
    case 'asset_code': {
      return compareStrings(toLowerText(left.asset_code), toLowerText(right.asset_code));
    }
    case 'name': {
      return compareStrings(toLowerText(left.name), toLowerText(right.name));
    }
    case 'category': {
      return compareStrings(
        toLowerText(normalizeAssetCategoryLiteral(left.category)),
        toLowerText(normalizeAssetCategoryLiteral(right.category)),
      );
    }
    case 'department': {
      return compareStrings(toLowerText(left.department), toLowerText(right.department));
    }
    case 'location': {
      return compareStrings(toLowerText(left.location), toLowerText(right.location));
    }
    case 'status': {
      return compareStrings(toLowerText(left.status), toLowerText(right.status));
    }
    default: {
      return 0;
    }
  }
}

export function isAssetSortField(value: unknown): value is AssetSortField {
  if (typeof value !== 'string') {
    return false;
  }

  return (
    value === 'asset_code' ||
    value === 'name' ||
    value === 'category' ||
    value === 'department' ||
    value === 'location' ||
    value === 'status' ||
    value === 'purchase_amount' ||
    value === 'purchase_date'
  );
}

export function isAssetFilterField(value: unknown): value is keyof AssetListFilters {
  return typeof value === 'string' && FILTERABLE_FIELDS.has(value as keyof AssetListFilters);
}

export function isServerSortableField(field: AssetSortField): boolean {
  return SERVER_SORTABLE_FIELDS.has(field);
}

export function normalizeAssetCategoryLiteral(value: string): string {
  const withoutPrefix = value.startsWith(CATEGORY_I18N_PREFIX)
    ? value.slice(CATEGORY_I18N_PREFIX.length)
    : value;

  const canonical = withoutPrefix
    .trim()
    .toLowerCase()
    .replace(/[-\s]+/g, '_');

  if (KNOWN_CATEGORY_VALUES.has(canonical as AssetCategory)) {
    return canonical;
  }

  return withoutPrefix;
}

export function shouldUseClientGlobalMode(
  filters: AssetListFilters,
  sortState: AssetSortState | null,
): boolean {
  const hasSubstringFilters =
    filters.department.trim().length > 0 ||
    filters.location.trim().length > 0 ||
    filters.holder.trim().length > 0;

  if (hasSubstringFilters) {
    return true;
  }

  if (!sortState) {
    return false;
  }

  return CLIENT_ONLY_SORTABLE_FIELDS.has(sortState.field);
}

export function normalizeFilters(filters: AssetListFilters): AssetListFilters {
  return {
    q: filters.q.trim(),
    status: filters.status,
    category: filters.category,
    department: filters.department.trim(),
    location: filters.location.trim(),
    holder: filters.holder.trim(),
  };
}

export function buildBaseServerParams(filters: AssetListFilters): Omit<
  ListAssetsParams,
  'page' | 'perPage' | 'sort'
> {
  return {
    q: filters.q || undefined,
    status: filters.status,
    category: filters.category,
  };
}

export function buildServerSortParam(sortState: AssetSortState | null): string | undefined {
  if (!sortState || !isServerSortableField(sortState.field)) {
    return undefined;
  }

  return sortState.order === 'descend' ? `-${sortState.field}` : sortState.field;
}

export function applyLocalAssetFilters(
  assets: AssetRecord[],
  filters: AssetListFilters,
): AssetRecord[] {
  const query = toLowerText(filters.q);
  const category = filters.category;
  const departmentQuery = toLowerText(filters.department);
  const locationQuery = toLowerText(filters.location);
  const holderQuery = toLowerText(filters.holder);

  return assets.filter((asset) => {
    if (query) {
      const searchable = [asset.asset_code, asset.name, asset.model]
        .map((value) => toLowerText(value))
        .join(' ');
      if (!searchable.includes(query)) {
        return false;
      }
    }

    if (filters.status && asset.status !== filters.status) {
      return false;
    }

    if (
      category &&
      normalizeAssetCategoryLiteral(asset.category) !== normalizeAssetCategoryLiteral(category)
    ) {
      return false;
    }

    if (departmentQuery && !toLowerText(asset.department).includes(departmentQuery)) {
      return false;
    }

    if (locationQuery && !toLowerText(asset.location).includes(locationQuery)) {
      return false;
    }

    if (holderQuery) {
      const holderSearchText = toLowerText(asset.responsible_person?.name ?? asset.responsible_person_id);
      if (!holderSearchText.includes(holderQuery)) {
        return false;
      }
    }

    return true;
  });
}

export function applyLocalAssetSort(
  assets: AssetRecord[],
  sortState: AssetSortState | null,
): AssetRecord[] {
  if (!sortState) {
    return assets;
  }

  const sorted = [...assets].sort((left, right) => compareByField(left, right, sortState.field));

  if (sortState.order === 'descend') {
    sorted.reverse();
  }

  return sorted;
}

export function paginateAssets(
  assets: AssetRecord[],
  page: number,
  perPage: number,
): AssetRecord[] {
  const start = (page - 1) * perPage;
  return assets.slice(start, start + perPage);
}
