export const ASSET_PATHS = {
  list: "/assets",
  mine: "/assets/mine",
  detail: (assetId: string) => `/assets/${assetId}`,
  assign: (assetId: string) => `/assets/${assetId}/assign`,
  unassign: (assetId: string) => `/assets/${assetId}/unassign`,
  dispose: (assetId: string) => `/assets/${assetId}/dispose`,
} as const;
