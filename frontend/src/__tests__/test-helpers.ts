import { vi } from 'vitest';
import type { AssetRecord } from '@/api/assets';

export const holderUser = {
  id: "holder-1",
  email: "holder@example.com",
  name: "Holder",
  role: "holder" as const,
};

export const managerUser = {
  id: "manager-1",
  email: "manager@example.com",
  name: "Manager",
  role: "manager" as const,
};

export const mockApi = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
};

export function getOpenModalContent(): HTMLElement {
  const openModal = Array.from(document.querySelectorAll<HTMLElement>(".ant-modal")).find((modal) => {
    const wrap = modal.closest(".ant-modal-wrap") as HTMLElement | null;
    return wrap !== null && wrap.style.display !== "none";
  });

  if (!openModal) {
    throw new Error("Expected an open modal, but none was found.");
  }

  return openModal;
}

export function getModalField(modal: HTMLElement, selector: string): HTMLElement {
  const field = modal.querySelector<HTMLElement>(selector);

  if (!field) {
    throw new Error(`Expected modal field ${selector}, but none was found.`);
  }

  return field;
}

export function buildAssetResponse(assetCode: string, assetName: string, total: number) {
  return {
    data: [
      {
        id: `${assetCode}-id`,
        asset_code: assetCode,
        name: assetName,
        model: "Dell Latitude 7440",
        specs: "Intel Core i7, 16GB RAM, 512GB SSD",
        category: "computer",
        supplier: "Dell",
        purchase_date: "2026-01-01",
        purchase_amount: "42900.00",
        location: "Taipei HQ",
        department: "IT",
        activation_date: "2026-01-05",
        warranty_expiry: "2028-01-01",
        status: "in_use" as const,
        responsible_person_id: "holder-1",
        responsible_person: {
          id: "holder-1",
          name: "Alice Chen",
        },
        disposal_reason: null,
        version: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ] as AssetRecord[],
    meta: {
      total,
      page: 1,
      per_page: 5,
      total_pages: Math.ceil(total / 5),
    },
  };
}
