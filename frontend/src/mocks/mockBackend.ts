import { ApiError } from "../api/base-client";
import type {
  AssetAssignPayload,
  AssetCreatePayload,
  AssetDisposePayload,
  AssetRecord,
  AssetUnassignPayload,
  AssetUpdatePayload,
  ListAssetsParams,
  PaginatedAssetResponse,
} from "../api/assets/types";
import type {
  ListRepairRequestsParams,
  PaginatedRepairRequestResponse,
  RepairRequestApprovePayload,
  RepairRequestCompletePayload,
  RepairRequestDetailsPayload,
  RepairRequestRecord,
  RepairRequestRejectPayload,
  RepairRequestStatus,
} from "../api/repair-requests/types";
import type { ListUsersParams, PaginatedUsersResponse, UserRecord } from "../api/users/types";
import { loadSession } from "../auth/storage";
import { DUMMY_ASSETS, DUMMY_HOLDERS } from "./assets";

interface MockState {
  initialized: boolean;
  users: UserRecord[];
  assets: AssetRecord[];
  repairRequests: RepairRequestRecord[];
}

const state: MockState = {
  initialized: false,
  users: [],
  assets: [],
  repairRequests: [],
};

const DEFAULT_ASSET_PAGE = 1;
const DEFAULT_ASSET_PER_PAGE = 5;
const DEFAULT_REPAIR_PAGE = 1;
const DEFAULT_REPAIR_PER_PAGE = 20;
const DEFAULT_USER_PAGE = 1;
const DEFAULT_USER_PER_PAGE = 20;

function nowIso(): string {
  return new Date().toISOString();
}

function ensureState(): void {
  if (state.initialized) {
    return;
  }

  const createdAt = nowIso();
  const seededUsers: UserRecord[] = [
    {
      id: "mock-manager",
      email: "admin@example.com",
      name: "Admin Manager",
      role: "manager",
      department: "Operations",
      created_at: createdAt,
    },
    {
      id: "mock-holder",
      email: "holder@example.com",
      name: "Demo Holder",
      role: "holder",
      department: "Engineering",
      created_at: createdAt,
    },
    ...DUMMY_HOLDERS.map((holder) => ({
      id: holder.id,
      email: `${holder.label.toLowerCase().replace(/\s+/g, ".")}@example.com`,
      name: holder.label,
      role: "holder" as const,
      department: "Engineering",
      created_at: createdAt,
    })),
  ];

  const dedupedById = new Map<string, UserRecord>();
  seededUsers.forEach((user) => {
    dedupedById.set(user.id, user);
  });
  state.users = [...dedupedById.values()];

  state.assets = DUMMY_ASSETS.map((asset) => ({
    ...asset,
    responsible_person_id: asset.responsible_person?.id ?? null,
    responsible_person: asset.responsible_person ? { ...asset.responsible_person } : null,
  }));

  const pendingAsset = state.assets.find((asset) => asset.status === "pending_repair") ?? state.assets[0];
  const underRepairAsset =
    state.assets.find((asset) => asset.status === "under_repair") ?? state.assets[1] ?? state.assets[0];
  const inUseAsset = state.assets.find((asset) => asset.status === "in_use") ?? state.assets[2] ?? state.assets[0];

  const requesterId = pendingAsset?.responsible_person_id ?? DUMMY_HOLDERS[0]?.id ?? "mock-holder";
  const requesterName =
    state.users.find((user) => user.id === requesterId)?.name ??
    pendingAsset?.responsible_person?.name ??
    "Demo Holder";

  const secondRequesterId = underRepairAsset?.responsible_person_id ?? DUMMY_HOLDERS[1]?.id ?? requesterId;
  const secondRequesterName =
    state.users.find((user) => user.id === secondRequesterId)?.name ??
    underRepairAsset?.responsible_person?.name ??
    requesterName;

  state.repairRequests = [
    {
      id: "repair-mock-0001",
      asset_id: pendingAsset?.id ?? "",
      requester_id: requesterId,
      reviewer_id: null,
      status: "pending_review",
      fault_description: "Screen flickers when moving the charging cable.",
      repair_date: null,
      fault_content: null,
      repair_plan: null,
      repair_cost: null,
      repair_vendor: null,
      rejection_reason: null,
      completed_at: null,
      created_at: createdAt,
      updated_at: createdAt,
      version: 1,
      asset: {
        id: pendingAsset?.id ?? "",
        asset_code: pendingAsset?.asset_code ?? "AST-MOCK-00001",
        name: pendingAsset?.name ?? "Mock Asset",
      },
      requester: {
        id: requesterId,
        name: requesterName,
      },
      reviewer: null,
      images: [
        {
          id: "img-mock-0001",
          url: "/api/v1/images/img-mock-0001",
          uploaded_at: createdAt,
        },
        {
          id: "img-mock-0002",
          url: "/api/v1/images/img-mock-0002",
          uploaded_at: createdAt,
        },
      ],
    },
    {
      id: "repair-mock-0002",
      asset_id: underRepairAsset?.id ?? "",
      requester_id: secondRequesterId,
      reviewer_id: "mock-manager",
      status: "under_repair",
      fault_description: "Battery drains unusually fast.",
      repair_date: "2026-04-20",
      fault_content: "Battery health below expected threshold.",
      repair_plan: "Replace battery module.",
      repair_cost: "2800.00",
      repair_vendor: "TSMC Partner Repair Center",
      rejection_reason: null,
      completed_at: null,
      created_at: createdAt,
      updated_at: createdAt,
      version: 2,
      asset: {
        id: underRepairAsset?.id ?? "",
        asset_code: underRepairAsset?.asset_code ?? "AST-MOCK-00002",
        name: underRepairAsset?.name ?? "Mock Asset",
      },
      requester: {
        id: secondRequesterId,
        name: secondRequesterName,
      },
      reviewer: {
        id: "mock-manager",
        name: "Admin Manager",
      },
      images: [
        {
          id: "img-mock-0003",
          url: "/api/v1/images/img-mock-0003",
          uploaded_at: createdAt,
        },
      ],
    },
    {
      id: "repair-mock-0003",
      asset_id: inUseAsset?.id ?? "",
      requester_id: requesterId,
      reviewer_id: "mock-manager",
      status: "completed",
      fault_description: "External display disconnected intermittently.",
      repair_date: "2026-04-12",
      fault_content: "Loose connector detected and replaced.",
      repair_plan: "Replace connector and run stress test.",
      repair_cost: "1500.00",
      repair_vendor: "In-house IT",
      rejection_reason: null,
      completed_at: createdAt,
      created_at: createdAt,
      updated_at: createdAt,
      version: 3,
      asset: {
        id: inUseAsset?.id ?? "",
        asset_code: inUseAsset?.asset_code ?? "AST-MOCK-00003",
        name: inUseAsset?.name ?? "Mock Asset",
      },
      requester: {
        id: requesterId,
        name: requesterName,
      },
      reviewer: {
        id: "mock-manager",
        name: "Admin Manager",
      },
      images: [],
    },
  ];

  state.initialized = true;
}

function getCurrentUser() {
  const session = loadSession();
  if (!session) {
    throw new ApiError(401, "unauthorized", "Please sign in again");
  }
  return session.user;
}

function paginate<T>(items: T[], page: number, perPage: number) {
  const total = items.length;
  const start = (page - 1) * perPage;
  const end = start + perPage;
  return {
    data: items.slice(start, end),
    meta: {
      total,
      page,
      per_page: perPage,
      total_pages: total > 0 ? Math.ceil(total / perPage) : 0,
    },
  };
}

function assertVersion(actual: number, expected: number): void {
  if (actual !== expected) {
    throw new ApiError(409, "conflict", "Resource was modified by another user. Please refresh and try again.");
  }
}

function findAssetOrThrow(assetId: string): AssetRecord {
  const asset = state.assets.find((item) => item.id === assetId);
  if (!asset) {
    throw new ApiError(404, "not_found", "Asset not found");
  }
  return asset;
}

function findUserOrThrow(userId: string): UserRecord {
  const user = state.users.find((item) => item.id === userId);
  if (!user) {
    throw new ApiError(422, "validation_error", "Assigned user not found");
  }
  return user;
}

function findRepairRequestOrThrow(repairRequestId: string): RepairRequestRecord {
  const request = state.repairRequests.find((item) => item.id === repairRequestId);
  if (!request) {
    throw new ApiError(404, "not_found", "Repair request not found");
  }
  return request;
}

function toComparableText(value: string | null | undefined): string {
  return (value ?? "").toLowerCase();
}

function nextAssetCode(): string {
  const year = new Date().getFullYear();
  const prefix = `AST-${year}-`;
  const sequence =
    state.assets
      .map((asset) => {
        if (!asset.asset_code.startsWith(prefix)) {
          return 0;
        }
        const suffix = asset.asset_code.slice(prefix.length);
        const parsed = Number.parseInt(suffix, 10);
        return Number.isNaN(parsed) ? 0 : parsed;
      })
      .reduce((max, value) => Math.max(max, value), 0) + 1;
  return `${prefix}${String(sequence).padStart(5, "0")}`;
}

function touchAsset(asset: AssetRecord): void {
  asset.version += 1;
  asset.updated_at = nowIso();
}

function updateRepairStatusAssetSideEffects(
  repairRequest: RepairRequestRecord,
  nextStatus: RepairRequestStatus,
): void {
  const asset = findAssetOrThrow(repairRequest.asset_id);
  if (nextStatus === "under_repair") {
    asset.status = "under_repair";
    touchAsset(asset);
    return;
  }
  if (nextStatus === "rejected" || nextStatus === "completed") {
    asset.status = "in_use";
    touchAsset(asset);
  }
}

export function listAssets(params?: ListAssetsParams): PaginatedAssetResponse {
  ensureState();

  let filtered = [...state.assets];
  if (params?.q) {
    const keyword = toComparableText(params.q);
    filtered = filtered.filter(
      (asset) =>
        toComparableText(asset.asset_code).includes(keyword) ||
        toComparableText(asset.name).includes(keyword) ||
        toComparableText(asset.model).includes(keyword),
    );
  }
  if (params?.status) {
    filtered = filtered.filter((asset) => asset.status === params.status);
  }
  if (params?.category) {
    filtered = filtered.filter((asset) => asset.category === params.category);
  }
  if (params?.department) {
    filtered = filtered.filter((asset) => asset.department === params.department);
  }
  if (params?.location) {
    filtered = filtered.filter((asset) => asset.location === params.location);
  }
  if (params?.responsiblePersonId) {
    filtered = filtered.filter((asset) => asset.responsible_person_id === params.responsiblePersonId);
  }

  const page = params?.page ?? DEFAULT_ASSET_PAGE;
  const perPage = params?.perPage ?? DEFAULT_ASSET_PER_PAGE;
  return paginate(filtered, page, perPage);
}

export function listMyAssets(params?: ListAssetsParams): PaginatedAssetResponse {
  ensureState();
  const user = getCurrentUser();

  let holderId = user.id;
  let myAssets = state.assets.filter((asset) => asset.responsible_person_id === holderId);

  if (myAssets.length === 0 && user.role === "holder") {
    holderId = DUMMY_HOLDERS[0]?.id ?? holderId;
    myAssets = state.assets.filter((asset) => asset.responsible_person_id === holderId);
  }

  const withFilters = listAssets({
    ...params,
    responsiblePersonId: holderId,
  });

  return {
    ...withFilters,
    data: withFilters.data.filter((asset) => myAssets.some((item) => item.id === asset.id)),
  };
}

export function getAssetById(assetId: string): AssetRecord {
  ensureState();
  return findAssetOrThrow(assetId);
}

export function createAsset(payload: AssetCreatePayload): AssetRecord {
  ensureState();
  const now = nowIso();
  const asset: AssetRecord = {
    id: `mock-asset-${Date.now()}`,
    asset_code: nextAssetCode(),
    name: payload.name,
    model: payload.model,
    specs: payload.specs ?? null,
    category: payload.category,
    supplier: payload.supplier,
    purchase_date: payload.purchase_date,
    purchase_amount: payload.purchase_amount,
    location: payload.location ?? "",
    department: payload.department ?? "",
    activation_date: payload.activation_date ?? null,
    warranty_expiry: payload.warranty_expiry ?? null,
    status: "in_stock",
    responsible_person_id: null,
    responsible_person: null,
    disposal_reason: null,
    version: 1,
    created_at: now,
    updated_at: now,
  };
  state.assets.unshift(asset);
  return asset;
}

export function updateAsset(assetId: string, payload: AssetUpdatePayload): AssetRecord {
  ensureState();
  const asset = findAssetOrThrow(assetId);
  assertVersion(asset.version, payload.version);

  const patch: Partial<AssetRecord> = {};
  if (payload.name !== undefined) patch.name = payload.name;
  if (payload.model !== undefined) patch.model = payload.model;
  if (payload.specs !== undefined) patch.specs = payload.specs;
  if (payload.category !== undefined) patch.category = payload.category;
  if (payload.supplier !== undefined) patch.supplier = payload.supplier;
  if (payload.purchase_date !== undefined) patch.purchase_date = payload.purchase_date;
  if (payload.purchase_amount !== undefined) patch.purchase_amount = payload.purchase_amount;
  if (payload.location !== undefined) patch.location = payload.location ?? "";
  if (payload.department !== undefined) patch.department = payload.department ?? "";
  if (payload.activation_date !== undefined) patch.activation_date = payload.activation_date;
  if (payload.warranty_expiry !== undefined) patch.warranty_expiry = payload.warranty_expiry;

  Object.assign(asset, patch);
  touchAsset(asset);
  return asset;
}

export function assignAsset(assetId: string, payload: AssetAssignPayload): AssetRecord {
  ensureState();
  const asset = findAssetOrThrow(assetId);
  const holder = findUserOrThrow(payload.responsible_person_id);
  assertVersion(asset.version, payload.version);

  if (holder.role !== "holder") {
    throw new ApiError(422, "validation_error", "Can only assign assets to holders");
  }
  if (asset.status !== "in_stock") {
    throw new ApiError(409, "invalid_transition", "Asset must be in stock before assignment");
  }

  asset.status = "in_use";
  asset.responsible_person_id = holder.id;
  asset.responsible_person = { id: holder.id, name: holder.name };
  if (payload.assignment_date) {
    asset.activation_date = payload.assignment_date;
  }
  touchAsset(asset);
  return asset;
}

export function unassignAsset(assetId: string, payload: AssetUnassignPayload): AssetRecord {
  ensureState();
  const asset = findAssetOrThrow(assetId);
  assertVersion(asset.version, payload.version);

  if (asset.status !== "in_use") {
    throw new ApiError(409, "invalid_transition", "Only in-use assets can be unassigned");
  }

  asset.status = "in_stock";
  asset.responsible_person_id = null;
  asset.responsible_person = null;
  touchAsset(asset);
  return asset;
}

export function disposeAsset(assetId: string, payload: AssetDisposePayload): AssetRecord {
  ensureState();
  const asset = findAssetOrThrow(assetId);
  assertVersion(asset.version, payload.version);

  if (asset.status !== "in_stock") {
    throw new ApiError(409, "invalid_transition", "Only in-stock assets can be disposed");
  }

  asset.status = "disposed";
  asset.disposal_reason = payload.disposal_reason;
  touchAsset(asset);
  return asset;
}

export function listUsers(params?: ListUsersParams): PaginatedUsersResponse {
  ensureState();

  let filtered = [...state.users];
  if (params?.role) {
    filtered = filtered.filter((user) => user.role === params.role);
  }
  if (params?.department) {
    filtered = filtered.filter((user) => user.department === params.department);
  }
  if (params?.q) {
    const keyword = toComparableText(params.q);
    filtered = filtered.filter(
      (user) =>
        toComparableText(user.name).includes(keyword) ||
        toComparableText(user.email).includes(keyword),
    );
  }

  const page = params?.page ?? DEFAULT_USER_PAGE;
  const perPage = params?.perPage ?? DEFAULT_USER_PER_PAGE;
  return paginate(filtered, page, perPage);
}

function applyRepairPatch(
  repairRequest: RepairRequestRecord,
  patch: Partial<RepairRequestRecord>,
): RepairRequestRecord {
  Object.assign(repairRequest, patch);
  repairRequest.version += 1;
  repairRequest.updated_at = nowIso();
  return repairRequest;
}

export function listRepairRequests(params?: ListRepairRequestsParams): PaginatedRepairRequestResponse {
  ensureState();
  const user = getCurrentUser();

  let filtered = [...state.repairRequests];
  if (user.role === "holder") {
    filtered = filtered.filter((item) => item.requester_id === user.id);
  }

  if (params?.status) {
    filtered = filtered.filter((item) => item.status === params.status);
  }
  if (params?.assetId) {
    filtered = filtered.filter((item) => item.asset_id === params.assetId);
  }
  if (params?.requesterId) {
    filtered = filtered.filter((item) => item.requester_id === params.requesterId);
  }

  if (params?.sort === "status") {
    filtered.sort((a, b) => a.status.localeCompare(b.status));
  } else if (params?.sort === "-status") {
    filtered.sort((a, b) => b.status.localeCompare(a.status));
  } else if (params?.sort === "created_at") {
    filtered.sort((a, b) => a.created_at.localeCompare(b.created_at));
  } else {
    filtered.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }

  const page = params?.page ?? DEFAULT_REPAIR_PAGE;
  const perPage = params?.perPage ?? DEFAULT_REPAIR_PER_PAGE;
  return paginate(filtered, page, perPage);
}

export function getRepairRequestById(repairRequestId: string): RepairRequestRecord {
  ensureState();
  const user = getCurrentUser();
  const repairRequest = findRepairRequestOrThrow(repairRequestId);

  if (user.role === "holder" && repairRequest.requester_id !== user.id) {
    throw new ApiError(403, "forbidden", "You do not have access to this repair request");
  }

  return repairRequest;
}

export function submitRepairRequest(payload: FormData): RepairRequestRecord {
  ensureState();
  const user = getCurrentUser();
  const assetId = (payload.get("asset_id") as string) || "";
  const faultDescription = (payload.get("fault_description") as string) || "";

  if (!assetId || !faultDescription) {
    throw new ApiError(422, "validation_error", "Missing required fields");
  }

  const asset = findAssetOrThrow(assetId);
  if (asset.status !== "in_use") {
    throw new ApiError(409, "invalid_state", "Asset must be in use to request repair");
  }

  const id = `repair-mock-${Math.random().toString(36).substr(2, 9)}`;
  const now = nowIso();

  // Simulate image processing
  const images = [];
  const files = payload.getAll("images");
  if (files && files.length > 0) {
    for (let i = 0; i < files.length; i++) {
      const imgId = `img-mock-new-${i}-${Math.random().toString(36).substr(2, 5)}`;
      images.push({
        id: imgId,
        url: `https://via.placeholder.com/300?text=Mock+Upload+${i + 1}`,
        uploaded_at: now,
      });
    }
  }

  const newRequest: RepairRequestRecord = {
    id,
    asset_id: assetId,
    requester_id: user.id,
    reviewer_id: null,
    status: "pending_review",
    fault_description: faultDescription,
    repair_date: null,
    fault_content: null,
    repair_plan: null,
    repair_cost: null,
    repair_vendor: null,
    rejection_reason: null,
    completed_at: null,
    created_at: now,
    updated_at: now,
    version: 1,
    asset: {
      id: asset.id,
      asset_code: asset.asset_code,
      name: asset.name,
    },
    requester: {
      id: user.id,
      name: user.name,
    },
    reviewer: null,
    images,
  };

  state.repairRequests.push(newRequest);
  asset.status = "pending_repair";
  touchAsset(asset);

  return newRequest;
}

export function approveRepairRequest(
  repairRequestId: string,
  payload: RepairRequestApprovePayload,
): RepairRequestRecord {
  ensureState();
  const user = getCurrentUser();
  const repairRequest = findRepairRequestOrThrow(repairRequestId);
  assertVersion(repairRequest.version, payload.version);

  if (repairRequest.status !== "pending_review") {
    throw new ApiError(409, "invalid_transition", "Repair request is not pending review");
  }

  const reviewerId = user.role === "manager" ? user.id : "mock-manager";
  const reviewerName = findUserOrThrow(reviewerId).name;

  applyRepairPatch(repairRequest, {
    status: "under_repair",
    reviewer_id: reviewerId,
    reviewer: { id: reviewerId, name: reviewerName },
    repair_plan: payload.repair_plan ?? repairRequest.repair_plan,
    repair_vendor: payload.repair_vendor ?? repairRequest.repair_vendor,
    repair_cost: payload.repair_cost ?? repairRequest.repair_cost,
    repair_date: payload.planned_date ?? repairRequest.repair_date,
  });
  updateRepairStatusAssetSideEffects(repairRequest, "under_repair");
  return repairRequest;
}

export function rejectRepairRequest(
  repairRequestId: string,
  payload: RepairRequestRejectPayload,
): RepairRequestRecord {
  ensureState();
  const user = getCurrentUser();
  const repairRequest = findRepairRequestOrThrow(repairRequestId);
  assertVersion(repairRequest.version, payload.version);

  if (repairRequest.status !== "pending_review") {
    throw new ApiError(409, "invalid_transition", "Repair request is not pending review");
  }

  const reviewerId = user.role === "manager" ? user.id : "mock-manager";
  const reviewerName = findUserOrThrow(reviewerId).name;

  applyRepairPatch(repairRequest, {
    status: "rejected",
    reviewer_id: reviewerId,
    reviewer: { id: reviewerId, name: reviewerName },
    rejection_reason: payload.rejection_reason ?? payload.reason,
    completed_at: nowIso(),
  });
  updateRepairStatusAssetSideEffects(repairRequest, "rejected");
  return repairRequest;
}

export function updateRepairRequestDetails(
  repairRequestId: string,
  payload: RepairRequestDetailsPayload,
): RepairRequestRecord {
  ensureState();
  const repairRequest = findRepairRequestOrThrow(repairRequestId);
  assertVersion(repairRequest.version, payload.version);

  if (repairRequest.status !== "under_repair") {
    throw new ApiError(409, "invalid_transition", "Repair request is not under repair");
  }

  const patch: Partial<RepairRequestRecord> = {};
  if (payload.repair_date !== undefined) patch.repair_date = payload.repair_date;
  if (payload.fault_content !== undefined) patch.fault_content = payload.fault_content;
  if (payload.repair_plan !== undefined) patch.repair_plan = payload.repair_plan;
  if (payload.repair_cost !== undefined) patch.repair_cost = payload.repair_cost;
  if (payload.repair_vendor !== undefined) patch.repair_vendor = payload.repair_vendor;

  applyRepairPatch(repairRequest, patch);
  return repairRequest;
}

export function completeRepairRequest(
  repairRequestId: string,
  payload: RepairRequestCompletePayload,
): RepairRequestRecord {
  ensureState();
  const repairRequest = findRepairRequestOrThrow(repairRequestId);
  assertVersion(repairRequest.version, payload.version);

  if (repairRequest.status !== "under_repair") {
    throw new ApiError(409, "invalid_transition", "Repair request is not under repair");
  }

  applyRepairPatch(repairRequest, {
    status: "completed",
    repair_date: payload.repair_date,
    fault_content: payload.fault_content,
    repair_plan: payload.repair_plan,
    repair_cost: payload.repair_cost,
    repair_vendor: payload.repair_vendor,
    completed_at: nowIso(),
  });
  updateRepairStatusAssetSideEffects(repairRequest, "completed");
  return repairRequest;
}
