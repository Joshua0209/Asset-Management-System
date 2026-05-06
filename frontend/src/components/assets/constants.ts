import type { AssetStatus } from '../../api/assets';

export const STATUS_COLORS: Record<AssetStatus, string> = {
  in_stock: 'default',
  in_use: 'success',
  pending_repair: 'processing',
  under_repair: 'warning',
  disposed: 'error',
};

export const PAGE_SIZE_OPTIONS = [5, 10, 20];
