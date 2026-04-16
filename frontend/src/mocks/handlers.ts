import { http, HttpResponse } from 'msw';
import type { User } from '@/types/user';
import type { Asset } from '@/types/asset';
import type { RepairRequest } from '@/types/repair';

// ─── Mock Data ───────────────────────────────────────────────────────────────

const mockManager: User = {
  id: 'u-001',
  email: 'manager@example.com',
  name: '王小明',
  role: 'manager',
  department: '資訊部',
  created_at: '2026-01-15T08:00:00Z',
};

const mockHolder: User = {
  id: 'u-002',
  email: 'holder@example.com',
  name: '李小華',
  role: 'holder',
  department: '業務部',
  created_at: '2026-02-01T08:00:00Z',
};

const mockAssets: Asset[] = [
  {
    id: 'a-001',
    asset_code: 'AST-2026-00001',
    name: 'MacBook Pro 16"',
    model: 'A2991',
    category: 'computer',
    status: 'in_use',
    specification: 'M4 Pro, 36GB RAM, 1TB SSD',
    supplier: 'Apple Taiwan',
    purchase_date: '2026-01-10',
    purchase_amount: '89900.00',
    warranty_expiry: '2029-01-10',
    location: '台北辦公室 3F',
    department: '業務部',
    responsible_person_id: 'u-002',
    responsible_person_name: '李小華',
    activation_date: '2026-01-15',
    notes: '',
    version: 1,
    created_at: '2026-01-10T08:00:00Z',
    updated_at: '2026-01-15T08:00:00Z',
  },
  {
    id: 'a-002',
    asset_code: 'AST-2026-00002',
    name: 'Dell UltraSharp 27"',
    model: 'U2723QE',
    category: 'monitor',
    status: 'in_stock',
    specification: '4K IPS, USB-C Hub',
    supplier: 'Dell Taiwan',
    purchase_date: '2026-02-01',
    purchase_amount: '18500.00',
    warranty_expiry: '2029-02-01',
    location: '台北辦公室 倉庫',
    department: '資訊部',
    responsible_person_id: null,
    responsible_person_name: null,
    activation_date: null,
    notes: '待分配',
    version: 1,
    created_at: '2026-02-01T08:00:00Z',
    updated_at: '2026-02-01T08:00:00Z',
  },
];

const mockRepairs: RepairRequest[] = [
  {
    id: 'r-001',
    asset_id: 'a-001',
    asset_code: 'AST-2026-00001',
    asset_name: 'MacBook Pro 16"',
    requester_id: 'u-002',
    requester_name: '李小華',
    reviewer_id: null,
    reviewer_name: null,
    status: 'pending_review',
    fault_description: '螢幕出現亮點，位於左上角區域',
    rejection_reason: null,
    repair_date: null,
    fault_content: null,
    repair_plan: null,
    repair_cost: null,
    repair_vendor: null,
    version: 1,
    created_at: '2026-03-15T10:30:00Z',
    updated_at: '2026-03-15T10:30:00Z',
  },
];

// ─── Handlers ────────────────────────────────────────────────────────────────

export const handlers = [
  // Auth
  http.post('/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    const user = body.email.includes('manager') ? mockManager : mockHolder;
    return HttpResponse.json({
      data: {
        access_token: 'mock-jwt-token',
        token_type: 'bearer',
        user,
      },
    });
  }),

  http.get('/api/v1/auth/me', () => {
    return HttpResponse.json({ data: mockManager });
  }),

  // Assets
  http.get('/api/v1/assets', () => {
    return HttpResponse.json({
      data: mockAssets,
      meta: { total: mockAssets.length, page: 1, per_page: 20, total_pages: 1 },
    });
  }),

  http.get('/api/v1/assets/:id', ({ params }) => {
    const asset = mockAssets.find((a) => a.id === params.id);
    if (!asset) {
      return HttpResponse.json(
        { error: { code: 'not_found', message: 'Asset not found' } },
        { status: 404 },
      );
    }
    return HttpResponse.json({ data: asset });
  }),

  // Repair Requests
  http.get('/api/v1/repair-requests', () => {
    return HttpResponse.json({
      data: mockRepairs,
      meta: { total: mockRepairs.length, page: 1, per_page: 20, total_pages: 1 },
    });
  }),

  http.get('/api/v1/repair-requests/:id', ({ params }) => {
    const repair = mockRepairs.find((r) => r.id === params.id);
    if (!repair) {
      return HttpResponse.json(
        { error: { code: 'not_found', message: 'Repair request not found' } },
        { status: 404 },
      );
    }
    return HttpResponse.json({ data: repair });
  }),

  http.post('/api/v1/repair-requests', () => {
    return HttpResponse.json({ data: mockRepairs[0] }, { status: 201 });
  }),
];
