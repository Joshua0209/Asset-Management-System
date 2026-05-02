import { request } from "../base-client";
import { USER_PATHS } from "./keys";
import type {
  ListUsersParams,
  PaginatedUsersResponse,
  UsersListResponse,
} from "./types";
import { listUsers as listUsersFromMockBackend } from "../../mocks/mockBackend";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";
const DEFAULT_PAGE = 1;
const DEFAULT_PER_PAGE = 20;

function buildListParams(params?: ListUsersParams) {
  return {
    page: params?.page ?? DEFAULT_PAGE,
    per_page: params?.perPage ?? DEFAULT_PER_PAGE,
    role: params?.role,
    department: params?.department,
    q: params?.q,
  };
}

function toPaginatedResponse(
  response: PaginatedUsersResponse | UsersListResponse,
  params?: ListUsersParams,
): PaginatedUsersResponse {
  if ("meta" in response) {
    return response;
  }

  const page = params?.page ?? DEFAULT_PAGE;
  const perPage = params?.perPage ?? DEFAULT_PER_PAGE;

  let filtered = [...response.data];
  if (params?.role) {
    filtered = filtered.filter((user) => user.role === params.role);
  }
  if (params?.department) {
    filtered = filtered.filter((user) => user.department === params.department);
  }
  if (params?.q) {
    const keyword = params.q.toLowerCase();
    filtered = filtered.filter(
      (user) =>
        user.name.toLowerCase().includes(keyword) || user.email.toLowerCase().includes(keyword),
    );
  }

  const total = filtered.length;
  const start = (page - 1) * perPage;
  return {
    data: filtered.slice(start, start + perPage),
    meta: {
      total,
      page,
      per_page: perPage,
      total_pages: total > 0 ? Math.ceil(total / perPage) : 0,
    },
  };
}

export async function listUsers(params?: ListUsersParams): Promise<PaginatedUsersResponse> {
  if (USE_MOCK_AUTH) {
    return listUsersFromMockBackend(params);
  }

  const response = await request<PaginatedUsersResponse | UsersListResponse>({
    method: "GET",
    url: USER_PATHS.list,
    params: buildListParams(params),
  });
  return toPaginatedResponse(response, params);
}
