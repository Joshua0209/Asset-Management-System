import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Space,
  Select,
  Table,
  Typography,
  notification,
} from 'antd';
import type { TableColumnsType, TableProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { ApiError, assetsApi, usersApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import { PAGE_SIZE_OPTIONS } from '../components/assets/constants';
import { getAssetColumns } from '../components/assets/columns';
import type {
  AssetCategory,
  AssetRecord,
  AssetStatus,
  ListAssetsParams,
  PaginatedAssetResponse,
} from '../api/assets';
import type { UserRecord } from '../api/users';
import AssetFormFields from '../components/assets/AssetFormFields';
import {
  ASSET_CATEGORY_OPTIONS,
  createWarrantyExpiryValidator,
  getAssetCategoryLabel,
  normalizeAssetFormValues,
  type AssetFormValues,
} from '../components/assets/assetFormShared';

const ASSET_STATUS_OPTIONS: AssetStatus[] = [
  'in_stock',
  'in_use',
  'pending_repair',
  'under_repair',
  'disposed',
];
const DEFAULT_TEXT_FILTERS = {
  q: '',
  department: '',
  location: '',
};
const TEXT_FILTER_DEBOUNCE_MS = 300;
const HOLDER_PAGE_SIZE = 100;
const CLIENT_FILTER_FETCH_PAGE_SIZE = 100;

type AssetSortField = 'asset_code' | 'name' | 'status' | 'purchase_amount' | 'purchase_date';
type AssetSortOrder = 'ascend' | 'descend' | null;
type AssetListFetcher = (params?: ListAssetsParams) => Promise<PaginatedAssetResponse>;

interface TextFilterState {
  q: string;
  department: string;
  location: string;
}

interface AssetSortState {
  field: AssetSortField | null;
  order: AssetSortOrder;
}

function toApiSort(sortState: AssetSortState): string | undefined {
  if (!sortState.field || !sortState.order || sortState.field === 'purchase_amount') {
    return undefined;
  }
  return `${sortState.order === 'descend' ? '-' : ''}${sortState.field}`;
}

function buildListParams(
  page: number,
  pageSize: number,
  q: string,
  status: AssetStatus | undefined,
  category: AssetCategory | undefined,
  responsiblePersonId: string | undefined,
  sort: string | undefined,
): ListAssetsParams {
  const params: ListAssetsParams = {
    page,
    perPage: pageSize,
  };

  if (q) {
    params.q = q;
  }
  if (status) {
    params.status = status;
  }
  if (category) {
    params.category = category;
  }
  if (responsiblePersonId) {
    params.responsiblePersonId = responsiblePersonId;
  }
  if (sort) {
    params.sort = sort;
  }

  return params;
}

function toNumericAmount(value: string | number): number {
  const parsed = Number.parseFloat(String(value));
  return Number.isFinite(parsed) ? parsed : 0;
}

function toComparableText(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

function matchesTextFilter(value: string | null | undefined, filterValue: string): boolean {
  if (!filterValue) {
    return true;
  }

  return toComparableText(value).includes(toComparableText(filterValue));
}

async function fetchAssetDataset(
  fetchFn: AssetListFetcher,
  params: ListAssetsParams,
  fetchAllPages: boolean,
): Promise<PaginatedAssetResponse> {
  if (!fetchAllPages) {
    return fetchFn(params);
  }

  const firstResponse = await fetchFn({
    ...params,
    page: 1,
    perPage: CLIENT_FILTER_FETCH_PAGE_SIZE,
  });

  if (firstResponse.meta.total_pages <= 1) {
    return {
      data: firstResponse.data,
      meta: {
        total: firstResponse.data.length,
        page: 1,
        per_page: CLIENT_FILTER_FETCH_PAGE_SIZE,
        total_pages: firstResponse.data.length > 0 ? 1 : 0,
      },
    };
  }

  const remainingPages = Array.from(
    { length: firstResponse.meta.total_pages - 1 },
    (_, index) => index + 2,
  );
  const remainingResponses = await Promise.all(
    remainingPages.map((nextPage) =>
      fetchFn({
        ...params,
        page: nextPage,
        perPage: CLIENT_FILTER_FETCH_PAGE_SIZE,
      }),
    ),
  );
  const data = [firstResponse, ...remainingResponses].flatMap((response) => response.data);

  return {
    data,
    meta: {
      total: data.length,
      page: 1,
      per_page: CLIENT_FILTER_FETCH_PAGE_SIZE,
      total_pages: data.length > 0 ? Math.ceil(data.length / CLIENT_FILTER_FETCH_PAGE_SIZE) : 0,
    },
  };
}

function isSortableField(field: unknown): field is AssetSortField {
  return (
    field === 'asset_code' ||
    field === 'name' ||
    field === 'status' ||
    field === 'purchase_amount' ||
    field === 'purchase_date'
  );
}

const AssetList: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [api, contextHolder] = notification.useNotification();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [textInputs, setTextInputs] = useState<TextFilterState>(DEFAULT_TEXT_FILTERS);
  const [textFilters, setTextFilters] = useState<TextFilterState>(DEFAULT_TEXT_FILTERS);
  const [statusFilter, setStatusFilter] = useState<AssetStatus | undefined>(undefined);
  const [categoryFilter, setCategoryFilter] = useState<AssetCategory | undefined>(undefined);
  const [responsiblePersonId, setResponsiblePersonId] = useState<string | undefined>(undefined);
  const [sortState, setSortState] = useState<AssetSortState>({ field: null, order: null });
  const [holders, setHolders] = useState<UserRecord[]>([]);
  const [holdersLoading, setHoldersLoading] = useState(false);
  const [assetForm] = Form.useForm<AssetFormValues>();

  const validatePurchaseAmount = createAmountValidator(t, { required: true });
  const validateWarrantyExpiry = useMemo(
    () => createWarrantyExpiryValidator(assetForm, t),
    [assetForm, t],
  );

  const formatApiError = (apiError: ApiError): string => getApiErrorMessage(apiError, t);

  const isManager = user?.role === 'manager';
  const apiSort = useMemo(() => toApiSort(sortState), [sortState]);
  const hasLocalTextFilters = Boolean(textFilters.department) || Boolean(textFilters.location);
  const requestParams = useMemo(
    () =>
      buildListParams(
        hasLocalTextFilters ? 1 : page,
        hasLocalTextFilters ? CLIENT_FILTER_FETCH_PAGE_SIZE : pageSize,
        textFilters.q,
        statusFilter,
        categoryFilter,
        responsiblePersonId,
        apiSort,
      ),
    [
      apiSort,
      categoryFilter,
      hasLocalTextFilters,
      page,
      pageSize,
      responsiblePersonId,
      statusFilter,
      textFilters.q,
    ],
  );
  const hasActiveControls =
    Boolean(textInputs.q) ||
    Boolean(textInputs.department) ||
    Boolean(textInputs.location) ||
    statusFilter !== undefined ||
    categoryFilter !== undefined ||
    responsiblePersonId !== undefined ||
    sortState.order !== null;

  useEffect(() => {
    setPage(1);
  }, [user?.role]);

  useEffect(() => {
    const timeoutId = globalThis.setTimeout(() => {
      const nextFilters = {
        q: textInputs.q.trim(),
        department: textInputs.department.trim(),
        location: textInputs.location.trim(),
      };

      if (
        nextFilters.q !== textFilters.q ||
        nextFilters.department !== textFilters.department ||
        nextFilters.location !== textFilters.location
      ) {
        setPage(1);
        setTextFilters(nextFilters);
      }
    }, TEXT_FILTER_DEBOUNCE_MS);

    return () => {
      globalThis.clearTimeout(timeoutId);
    };
  }, [textFilters, textInputs]);

  useEffect(() => {
    if (!isManager) {
      setHolders([]);
      setHoldersLoading(false);
      return;
    }

    let cancelled = false;
    const loadHolders = async () => {
      setHoldersLoading(true);
      try {
        const response = await usersApi.listUsers({
          page: 1,
          perPage: HOLDER_PAGE_SIZE,
          role: 'holder',
        });
        if (!cancelled) {
          setHolders(response.data);
        }
      } catch (e) {
        if (!cancelled && e instanceof ApiError) {
          api.error({
            title: t('assetList.manager.holdersLoadErrorTitle'),
            description: getApiErrorMessage(e, t),
          });
        }
      } finally {
        if (!cancelled) {
          setHoldersLoading(false);
        }
      }
    };

    void loadHolders();

    return () => {
      cancelled = true;
    };
  }, [api, isManager, t]);

  useEffect(() => {
    if (!user) {
      return;
    }

    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const fetchFn = user.role === 'manager' ? assetsApi.listAssets : assetsApi.listMyAssets;
        const response = await fetchAssetDataset(fetchFn, requestParams, hasLocalTextFilters);
        if (cancelled) {
          return;
        }
        setAssets(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) {
          return;
        }
        setAssets([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(getApiErrorMessage(e, t));
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, [hasLocalTextFilters, requestParams, t, user]);

  const reloadCurrentPage = async () => {
    if (!user) {
      return;
    }

    const fetchFn = user.role === 'manager' ? assetsApi.listAssets : assetsApi.listMyAssets;
    const response = await fetchAssetDataset(fetchFn, requestParams, hasLocalTextFilters);
    setAssets(response.data);
    setTotal(response.meta.total);
  };

  const filteredAssets = useMemo(() => {
    if (!hasLocalTextFilters) {
      return assets;
    }

    return assets.filter(
      (asset) =>
        matchesTextFilter(asset.department, textFilters.department) &&
        matchesTextFilter(asset.location, textFilters.location),
    );
  }, [assets, hasLocalTextFilters, textFilters.department, textFilters.location]);

  const paginatedAssets = useMemo(() => {
    if (!hasLocalTextFilters) {
      return assets;
    }

    const startIndex = (page - 1) * pageSize;
    return filteredAssets.slice(startIndex, startIndex + pageSize);
  }, [assets, filteredAssets, hasLocalTextFilters, page, pageSize]);

  const displayTotal = hasLocalTextFilters ? filteredAssets.length : total;

  const displayedAssets = useMemo(() => {
    const sourceAssets = hasLocalTextFilters ? paginatedAssets : assets;

    if (sortState.field !== 'purchase_amount' || sortState.order === null) {
      return sourceAssets;
    }

    return [...sourceAssets].sort((left, right) => {
      const amountDiff = toNumericAmount(left.purchase_amount) - toNumericAmount(right.purchase_amount);
      return sortState.order === 'ascend' ? amountDiff : -amountDiff;
    });
  }, [assets, hasLocalTextFilters, paginatedAssets, sortState]);

  const openCreateModal = () => {
    assetForm.resetFields();
    setIsAssetModalOpen(true);
  };

  const handleSaveAsset = async () => {
    try {
      const values = await assetForm.validateFields();
      const payload = normalizeAssetFormValues(values);
      setIsSubmitting(true);

      await assetsApi.createAsset(payload);

      setIsAssetModalOpen(false);
      await reloadCurrentPage();
      api.success({ title: t('assetList.manager.createSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const actionsColumn: TableColumnsType<AssetRecord>[number] = {
    title: t('assetList.columns.actions'),
    key: 'actions',
    width: 110,
    render: (_: unknown, asset: AssetRecord) => (
      <Space size={4} wrap>
        <Button type="link" onClick={() => navigate(`/assets/${asset.id}`)}>
          {t('assetList.actions.detail')}
        </Button>
      </Space>
    ),
  };

  const columns: TableColumnsType<AssetRecord> = [
    ...getAssetColumns(t).map((column) => {
      if (
        column.key === 'asset_code' ||
        column.key === 'name' ||
        column.key === 'status' ||
        column.key === 'purchase_amount' ||
        column.key === 'purchase_date'
      ) {
        return {
          ...column,
          sorter: true,
          sortOrder: sortState.field === column.key ? sortState.order : null,
        };
      }
      return column;
    }),
    actionsColumn,
  ];

  const handleTableChange: TableProps<AssetRecord>['onChange'] = (
    pagination,
    _filters,
    sorter,
    extra,
  ) => {
    const nextPage = pagination.current ?? page;
    const nextPageSize = pagination.pageSize ?? pageSize;

    if (extra.action === 'sort') {
      const nextSorter = Array.isArray(sorter) ? sorter[0] : sorter;
      const nextOrder = nextSorter.order ?? null;
      const nextField = isSortableField(nextSorter.columnKey) ? nextSorter.columnKey : null;

      setPageSize(nextPageSize);
      setPage(1);
      setSortState(nextOrder && nextField ? { field: nextField, order: nextOrder } : { field: null, order: null });
      return;
    }

    setPage(nextPage);
    setPageSize(nextPageSize);
  };

  const resetControls = () => {
    setTextInputs(DEFAULT_TEXT_FILTERS);
    setTextFilters(DEFAULT_TEXT_FILTERS);
    setStatusFilter(undefined);
    setCategoryFilter(undefined);
    setResponsiblePersonId(undefined);
    setSortState({ field: null, order: null });
    setPage(1);
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert title={error} type="error" showIcon /> : null}

      <Card>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {isManager ? (
            <Space>
              <Button type="primary" onClick={openCreateModal}>
                {t('assetList.manager.createButton')}
              </Button>
            </Space>
          ) : null}

          <Space wrap size={[12, 12]}>
            <Input
              allowClear
              data-testid="asset-search-filter"
              aria-label={t('assetList.filters.searchLabel')}
              placeholder={t('assetList.filters.searchPlaceholder')}
              style={{ width: 260 }}
              value={textInputs.q}
              onChange={(event) => {
                setTextInputs((current) => ({
                  ...current,
                  q: event.target.value,
                }));
              }}
            />
            <Select
              allowClear
              data-testid="asset-status-filter"
              aria-label={t('assetList.filters.statusLabel')}
              placeholder={t('assetList.filters.statusPlaceholder')}
              style={{ width: 180 }}
              value={statusFilter}
              onChange={(value) => {
                setPage(1);
                setStatusFilter(value);
              }}
              options={ASSET_STATUS_OPTIONS.map((status) => ({
                value: status,
                label: t(`assetList.status.${status}`),
              }))}
            />
            <Select
              allowClear
              data-testid="asset-category-filter"
              aria-label={t('assetList.filters.categoryLabel')}
              placeholder={t('assetList.filters.categoryPlaceholder')}
              style={{ width: 180 }}
              value={categoryFilter}
              onChange={(value) => {
                setPage(1);
                setCategoryFilter(value);
              }}
              options={ASSET_CATEGORY_OPTIONS.map((category) => ({
                value: category,
                label: getAssetCategoryLabel(t, category),
              }))}
            />
            <Input
              allowClear
              data-testid="asset-department-filter"
              aria-label={t('assetList.filters.departmentLabel')}
              placeholder={t('assetList.filters.departmentPlaceholder')}
              style={{ width: 180 }}
              value={textInputs.department}
              onChange={(event) => {
                setTextInputs((current) => ({
                  ...current,
                  department: event.target.value,
                }));
              }}
            />
            <Input
              allowClear
              data-testid="asset-location-filter"
              aria-label={t('assetList.filters.locationLabel')}
              placeholder={t('assetList.filters.locationPlaceholder')}
              style={{ width: 180 }}
              value={textInputs.location}
              onChange={(event) => {
                setTextInputs((current) => ({
                  ...current,
                  location: event.target.value,
                }));
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              data-testid="asset-holder-filter"
              aria-label={t('assetList.filters.holderLabel')}
              placeholder={t('assetList.filters.holderPlaceholder')}
              style={{ width: 220 }}
              loading={holdersLoading}
              value={responsiblePersonId}
              onChange={(value) => {
                setPage(1);
                setResponsiblePersonId(value);
              }}
              options={holders.map((holder) => ({
                value: holder.id,
                label: `${holder.name} (${holder.department})`,
              }))}
            />
            <Button onClick={resetControls} disabled={!hasActiveControls}>
              {t('assetList.filters.resetButton')}
            </Button>
          </Space>

          {sortState.field === 'purchase_amount' && sortState.order !== null ? (
            <Typography.Text type="secondary">
              {t('assetList.filters.purchaseAmountSortHint')}
            </Typography.Text>
          ) : null}

          <Typography.Text type="secondary">
            {t('assetList.summary', { count: displayTotal })}
          </Typography.Text>

          <Table<AssetRecord>
            rowKey="id"
            loading={loading}
            dataSource={displayedAssets}
            columns={columns}
            locale={{
              emptyText: t('assetList.empty'),
            }}
            pagination={{
              current: page,
              pageSize,
              total: displayTotal,
              pageSizeOptions: PAGE_SIZE_OPTIONS.map(String),
              showSizeChanger: true,
              showTotal: (total) => t('assetList.pagination.total', { count: total }),
            }}
            onChange={handleTableChange}
            scroll={{ x: 1200 }}
          />

          <Modal
            open={isAssetModalOpen}
            title={t('assetList.manager.createTitle')}
            onCancel={() => setIsAssetModalOpen(false)}
            onOk={() => void handleSaveAsset()}
            okText={t('common.button.save')}
            cancelText={t('common.button.cancel')}
            confirmLoading={isSubmitting}
            destroyOnHidden
            forceRender
          >
            <Form form={assetForm} layout="vertical">
              <AssetFormFields
                t={t}
                validatePurchaseAmount={validatePurchaseAmount}
                validateWarrantyExpiry={validateWarrantyExpiry}
              />
            </Form>
          </Modal>
        </Space>
      </Card>
    </Space>
  );
};

export default AssetList;
