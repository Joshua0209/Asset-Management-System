import { request } from "../base-client";
import { loadSession } from "../../auth/storage";
import { DUMMY_ASSETS, DUMMY_HOLDERS, type AssetRecord as MockAssetRecord } from "../../mocks/assets";
import { ASSET_PATHS } from "./keys";
import type { ListAssetsParams, PaginatedAssetResponse } from "./types";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";
const DEFAULT_PAGE = 1;
const DEFAULT_PER_PAGE = 5;
const MOCK_DELAY_MS = 120;

const sleep = (ms: number) => new Promise<void>((resolve) => globalThis.setTimeout(resolve, ms));

function buildListParams(params?: ListAssetsParams): { page: number; per_page: number } {
  return {
    page: params?.page ?? DEFAULT_PAGE,
    per_page: params?.perPage ?? DEFAULT_PER_PAGE,
  };
}

function toApiAsset(asset: MockAssetRecord) {
  return {
    ...asset,
    responsible_person_id: asset.responsible_person?.id ?? null,
  };
}

function paginateMockAssets(items: MockAssetRecord[], params?: ListAssetsParams): PaginatedAssetResponse {
  const page = params?.page ?? DEFAULT_PAGE;
  const perPage = params?.perPage ?? DEFAULT_PER_PAGE;
  const total = items.length;
  const start = (page - 1) * perPage;
  const end = start + perPage;
  return {
    data: items.slice(start, end).map(toApiAsset),
    meta: {
      total,
      page,
      per_page: perPage,
      total_pages: total ? Math.ceil(total / perPage) : 0,
    },
  };
}

export async function listAssets(params?: ListAssetsParams): Promise<PaginatedAssetResponse> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return paginateMockAssets(DUMMY_ASSETS, params);
  }

  return request<PaginatedAssetResponse>({
    method: "GET",
    url: ASSET_PATHS.list,
    params: buildListParams(params),
  });
}

export async function listMyAssets(params?: ListAssetsParams): Promise<PaginatedAssetResponse> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    const session = loadSession();
    const holderId = session?.user.id;

    let myAssets = DUMMY_ASSETS.filter((asset) => asset.responsible_person?.id === holderId);

    // Keep holder mock mode useful even if mock auth user IDs differ from dummy holder IDs.
    if (myAssets.length === 0 && session?.user.role === "holder") {
      myAssets = DUMMY_ASSETS.filter(
        (asset) => asset.responsible_person?.id === DUMMY_HOLDERS[0]?.id,
      );
    }

    return paginateMockAssets(myAssets, params);
  }

  return request<PaginatedAssetResponse>({
    method: "GET",
    url: ASSET_PATHS.mine,
    params: buildListParams(params),
  });
}
