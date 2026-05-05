import { ApiError, type ErrorDetail, request } from "../base-client";
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
const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const sleep = (ms: number) => new Promise<void>((resolve) => globalThis.setTimeout(resolve, ms));

function parseDateOnly(value?: string | null): Date | null {
  if (!value || !DATE_ONLY_PATTERN.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function todayUtcDate(): Date {
  const date = new Date();
  date.setUTCHours(0, 0, 0, 0);
  return date;
}

function validationError(field: string, message: string): never {
  const details: ErrorDetail[] = [{ field, message, code: "invalid_value" }];
  throw new ApiError(422, "validation_error", message, details);
}

function assertMaxLength(
  value: string | null | undefined,
  max: number,
  field: string,
  label: string,
): void {
  if (value !== undefined && value !== null && value.length > max) {
    validationError(field, `${label} must be at most ${max} characters.`);
  }
}

function assertRequiredString(value: string | null | undefined, field: string, label: string): void {
  if (value === undefined || value === null || value.trim() === "") {
    validationError(field, `${label} is required.`);
  }
}

function assertPurchaseAmount(value: string | number | undefined, field = "purchase_amount"): void {
  if (value === undefined) {
    return;
  }
  const normalized = String(value).trim();
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) {
    validationError(field, "purchase_amount must be a positive number with up to 2 decimal places.");
  }
  const parsed = Number.parseFloat(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    validationError(field, "purchase_amount must be greater than 0.");
  }
  const digits = normalized.replace('.', '').replace(/^0+/, '').length;
  if (digits > 15) {
    validationError(field, "purchase_amount must have at most 15 digits in total.");
  }
}

function assertPurchaseDateNotFuture(value: string | undefined): void {
  if (value === undefined) {
    return;
  }
  const parsed = parseDateOnly(value);
  if (!parsed) {
    validationError("purchase_date", "purchase_date must be a valid ISO date.");
  }
  if (parsed.getTime() > todayUtcDate().getTime()) {
    validationError("purchase_date", "purchase_date must not be in the future.");
  }
}

function assertWarrantyOrder(
  warrantyExpiry: string | null | undefined,
  purchaseDate: string | undefined,
  activationDate: string | null | undefined,
): void {
  if (!warrantyExpiry) {
    return;
  }
  const warranty = parseDateOnly(warrantyExpiry);
  if (!warranty) {
    validationError("warranty_expiry", "warranty_expiry must be a valid ISO date.");
  }

  const purchase = parseDateOnly(purchaseDate);
  if (purchase && warranty.getTime() <= purchase.getTime()) {
    validationError("warranty_expiry", "warranty_expiry must be after purchase_date.");
  }

  const activation = parseDateOnly(activationDate);
  if (activation && warranty.getTime() <= activation.getTime()) {
    validationError("warranty_expiry", "warranty_expiry must be after activation_date.");
  }
}

function validateCreatePayload(payload: AssetCreatePayload): void {
  assertRequiredString(payload.name, "name", "name");
  assertRequiredString(payload.model, "model", "model");
  assertRequiredString(payload.supplier, "supplier", "supplier");
  assertMaxLength(payload.name, 120, "name", "name");
  assertMaxLength(payload.model, 120, "model", "model");
  assertMaxLength(payload.specs, 500, "specs", "specs");
  assertMaxLength(payload.supplier, 120, "supplier", "supplier");
  assertMaxLength(payload.location, 120, "location", "location");
  assertMaxLength(payload.department, 100, "department", "department");
  assertPurchaseDateNotFuture(payload.purchase_date);
  assertPurchaseAmount(payload.purchase_amount);
  assertWarrantyOrder(payload.warranty_expiry, payload.purchase_date, payload.activation_date);
}

function validateUpdatePayload(payload: AssetUpdatePayload): void {
  if (payload.name !== undefined) {
    assertRequiredString(payload.name, "name", "name");
  }
  if (payload.model !== undefined) {
    assertRequiredString(payload.model, "model", "model");
  }
  if (payload.supplier !== undefined) {
    assertRequiredString(payload.supplier, "supplier", "supplier");
  }
  assertMaxLength(payload.name, 120, "name", "name");
  assertMaxLength(payload.model, 120, "model", "model");
  assertMaxLength(payload.specs, 500, "specs", "specs");
  assertMaxLength(payload.supplier, 120, "supplier", "supplier");
  assertMaxLength(payload.location, 120, "location", "location");
  assertMaxLength(payload.department, 100, "department", "department");
  assertPurchaseDateNotFuture(payload.purchase_date);
  assertPurchaseAmount(payload.purchase_amount);
  assertWarrantyOrder(payload.warranty_expiry, payload.purchase_date, payload.activation_date);
}

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
  validateCreatePayload(payload);

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
  validateUpdatePayload(payload);

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
