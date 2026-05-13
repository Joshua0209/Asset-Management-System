import { request } from "../base-client";
import {
  approveRepairRequest as approveRepairRequestFromMockBackend,
  completeRepairRequest as completeRepairRequestFromMockBackend,
  getRepairRequestById as getRepairRequestByIdFromMockBackend,
  listRepairRequests as listRepairRequestsFromMockBackend,
  rejectRepairRequest as rejectRepairRequestFromMockBackend,
  submitRepairRequest as submitRepairRequestFromMockBackend,
  updateRepairRequestDetails as updateRepairRequestDetailsFromMockBackend,
} from "../../mocks/mockBackend";
import { REPAIR_REQUEST_PATHS } from "./keys";
import type {
  ListRepairRequestsParams,
  PaginatedRepairRequestResponse,
  RepairRequestApprovePayload,
  RepairRequestCompletePayload,
  RepairRequestDataResponse,
  RepairRequestDetailsPayload,
  RepairRequestRecord,
  RepairRequestRejectPayload,
} from "./types";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";
const DEFAULT_PAGE = 1;
const DEFAULT_PER_PAGE = 20;

function buildListParams(params?: ListRepairRequestsParams) {
  return {
    page: params?.page ?? DEFAULT_PAGE,
    per_page: params?.perPage ?? DEFAULT_PER_PAGE,
    status: params?.status,
    asset_id: params?.assetId,
    requester_id: params?.requesterId,
    sort: params?.sort,
  };
}

function unwrapRepairResponse(
  response: RepairRequestDataResponse | RepairRequestRecord,
): RepairRequestRecord {
  if ("data" in response) {
    return response.data;
  }
  return response;
}

export async function getRepairRequestById(id: string): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return getRepairRequestByIdFromMockBackend(id);
  }

  const response = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "GET",
    url: REPAIR_REQUEST_PATHS.detail(id),
  });
  return unwrapRepairResponse(response);
}

export async function listRepairRequests(
  params?: ListRepairRequestsParams,
): Promise<PaginatedRepairRequestResponse> {
  if (USE_MOCK_AUTH) {
    return listRepairRequestsFromMockBackend(params);
  }

  return request<PaginatedRepairRequestResponse>({
    method: "GET",
    url: REPAIR_REQUEST_PATHS.list,
    params: buildListParams(params),
  });
}

export async function approveRepairRequest(
  id: string,
  payload: RepairRequestApprovePayload,
): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return approveRepairRequestFromMockBackend(id, payload);
  }

  const approved = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "POST",
    url: REPAIR_REQUEST_PATHS.approve(id),
    data: {
      version: payload.version,
    },
  });

  if (
    payload.repair_plan ||
    payload.repair_vendor ||
    payload.repair_cost !== undefined ||
    payload.planned_date
  ) {
    const approvedRequest = unwrapRepairResponse(approved);
    const detailPayload: RepairRequestDetailsPayload = {
      version: approvedRequest.version,
    };

    if (payload.planned_date !== undefined) {
      detailPayload.repair_date = payload.planned_date;
    }
    if (payload.repair_plan !== undefined) {
      detailPayload.repair_plan = payload.repair_plan;
    }
    if (payload.repair_cost !== undefined) {
      detailPayload.repair_cost = payload.repair_cost;
    }
    if (payload.repair_vendor !== undefined) {
      detailPayload.repair_vendor = payload.repair_vendor;
    }

    return updateRepairRequestDetails(id, {
      ...detailPayload,
    });
  }

  return unwrapRepairResponse(approved);
}

export async function rejectRepairRequest(
  id: string,
  payload: RepairRequestRejectPayload,
): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return rejectRepairRequestFromMockBackend(id, payload);
  }

  const response = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "POST",
    url: REPAIR_REQUEST_PATHS.reject(id),
    data: {
      version: payload.version,
      rejection_reason: payload.rejection_reason ?? payload.reason ?? "",
    },
  });
  return unwrapRepairResponse(response);
}

export async function updateRepairRequestDetails(
  id: string,
  payload: RepairRequestDetailsPayload,
): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return updateRepairRequestDetailsFromMockBackend(id, payload);
  }

  const response = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "PATCH",
    url: REPAIR_REQUEST_PATHS.repairDetails(id),
    data: payload,
  });
  return unwrapRepairResponse(response);
}

export async function completeRepairRequest(
  id: string,
  payload: RepairRequestCompletePayload,
): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return completeRepairRequestFromMockBackend(id, payload);
  }

  const response = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "POST",
    url: REPAIR_REQUEST_PATHS.complete(id),
    data: payload,
  });
  return unwrapRepairResponse(response);
}

export async function submitRepairRequest(
  payload: FormData,
): Promise<RepairRequestRecord> {
  if (USE_MOCK_AUTH) {
    return submitRepairRequestFromMockBackend(payload);
  }

  const response = await request<RepairRequestDataResponse | RepairRequestRecord>({
    method: "POST",
    url: REPAIR_REQUEST_PATHS.list,
    data: payload,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return unwrapRepairResponse(response);
}
