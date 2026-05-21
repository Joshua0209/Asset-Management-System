import type { AssetStatus } from '@/api/assets';
import { designStatusColors } from '@/design/antdTheme';

export const STATUS_COLORS: Record<AssetStatus, string> = {
  in_stock: designStatusColors.asset.inStock,
  in_use: designStatusColors.asset.inUse,
  pending_repair: designStatusColors.asset.pendingRepair,
  under_repair: designStatusColors.asset.underRepair,
  disposed: designStatusColors.asset.disposed,
};

export const PAGE_SIZE_OPTIONS = [5, 10, 20];
