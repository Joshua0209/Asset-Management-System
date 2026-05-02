import { request } from "../base-client";
import {
  assignAsset as assignAssetFromMockBackend,
  createAsset as createAssetFromMockBackend,
  disposeAsset as disposeAssetFromMockBackend,
  getAssetById as getAssetByIdFromMockBackend,
  listAssets as listAssetsFromMockBackend,
  listMyAssets as listMyAssetsFromMockBackend,
  unassignAsset as unassignAssetFromMockBackend,
  updateAsset as updateAssetFromMockBackend,
} from "../../mocks/mockBackend";
import { ASSET_PATHS } from "./keys";
import type {
  AssetAssignPayload,
  AssetCreatePayload,
  AssetDataResponse,
  AssetDisposePayload,
  AssetRecord,
  AssetUnassignPayload,
  AssetUpdatePayload,
  ListAssetsParams,
  PaginatedAssetResponse,
} from "./types";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";
const DEFAULT_PAGE = 1;
const DEFAULT_PER_PAGE = 5;
const MOCK_DELAY_MS = 120;

const sleep = (ms: number) => new Promise<void>((resolve) => globalThis.setTimeout(resolve, ms));

function buildListParams(params?: ListAssetsParams) {
  return {
    page: params?.page ?? DEFAULT_PAGE,
    per_page: params?.perPage ?? DEFAULT_PER_PAGE,
    q: params?.q,
    status: params?.status,
    category: params?.category,
    department: params?.department,
    location: params?.location,
    responsible_person_id: params?.responsiblePersonId,
    sort: params?.sort,
  };
}

export async function listAssets(params?: ListAssetsParams): Promise<PaginatedAssetResponse> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return listAssetsFromMockBackend(params);
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
    return listMyAssetsFromMockBackend(params);
  }

  return request<PaginatedAssetResponse>({
    method: "GET",
    url: ASSET_PATHS.mine,
    params: buildListParams(params),
  });
}

export async function getAssetById(assetId: string): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return getAssetByIdFromMockBackend(assetId);
  }

  const response = await request<AssetDataResponse>({
    method: "GET",
    url: ASSET_PATHS.detail(assetId),
  });
  return response.data;
}

export async function createAsset(payload: AssetCreatePayload): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return createAssetFromMockBackend(payload);
  }

  const response = await request<AssetDataResponse>({
    method: "POST",
    url: ASSET_PATHS.list,
    data: payload,
  });
  return response.data;
}

export async function updateAsset(assetId: string, payload: AssetUpdatePayload): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return updateAssetFromMockBackend(assetId, payload);
  }

  const response = await request<AssetDataResponse>({
    method: "PATCH",
    url: ASSET_PATHS.detail(assetId),
    data: payload,
  });
  return response.data;
}

export async function assignAsset(assetId: string, payload: AssetAssignPayload): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return assignAssetFromMockBackend(assetId, payload);
  }

  const response = await request<AssetDataResponse>({
    method: "POST",
    url: ASSET_PATHS.assign(assetId),
    data: payload,
  });
  return response.data;
}

export async function unassignAsset(
  assetId: string,
  payload: AssetUnassignPayload,
): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return unassignAssetFromMockBackend(assetId, payload);
  }

  const response = await request<AssetDataResponse>({
    method: "POST",
    url: ASSET_PATHS.unassign(assetId),
    data: payload,
  });
  return response.data;
}

export async function disposeAsset(assetId: string, payload: AssetDisposePayload): Promise<AssetRecord> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    return disposeAssetFromMockBackend(assetId, payload);
  }

  const response = await request<AssetDataResponse>({
    method: "POST",
    url: ASSET_PATHS.dispose(assetId),
    data: payload,
  });
  return response.data;
}
