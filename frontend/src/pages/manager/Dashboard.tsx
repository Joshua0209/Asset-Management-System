import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  List,
  Progress,
  Row,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ApiError, dashboardApi } from "@/api";
import type { ManagerDashboard } from "@/api/dashboard";
import { getApiErrorMessage } from "@/utils/apiErrors";
import { formatDateTime } from "@/utils/format";

const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [data, setData] = useState<ManagerDashboard | null>(null);
  const [isMock, setIsMock] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await dashboardApi.getManagerDashboard();
      setData(result.data);
      setIsMock(result.isMock);
    } catch (err) {
      const message =
        err instanceof ApiError ? getApiErrorMessage(err, t) : t("dashboard.loadError");
      // Preserve the raw error in the console so developers see network
      // failures or parse errors instead of just the localised string.
      // eslint-disable-next-line no-console
      console.error("Failed to load manager dashboard", err);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  // Use the largest bucket as the denominator so the bars stay comparable
  // within the chart rather than scaled to an arbitrary fixed cap.
  const maxCategoryCount = useMemo(() => {
    if (!data || data.asset_categories.length === 0) return 0;
    return Math.max(...data.asset_categories.map((c) => c.count));
  }, [data]);

  if (loading && !data) {
    return (
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Typography.Title level={2} style={{ marginBottom: 0 }}>
          {t("common.nav.dashboard")}
        </Typography.Title>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Space>
    );
  }

  if (error) {
    return (
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Typography.Title level={2} style={{ marginBottom: 0 }}>
          {t("common.nav.dashboard")}
        </Typography.Title>
        <Alert
          type="error"
          showIcon
          message={error}
          action={
            <Button size="small" onClick={() => void load()}>
              {t("dashboard.retry")}
            </Button>
          }
        />
      </Space>
    );
  }

  if (!data) return null;

  const { kpis, asset_categories, repair_summary, recent_pending_repairs } = data;
  const inUseRatio = kpis.total_assets > 0 ? (kpis.in_use_assets / kpis.total_assets) * 100 : 0;
  const underRepairRatio =
    kpis.total_assets > 0 ? (kpis.under_repair_assets / kpis.total_assets) * 100 : 0;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t("common.nav.dashboard")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t("dashboard.description")}
      </Typography.Paragraph>

      {isMock && (
        <Alert
          type="warning"
          showIcon
          message={t("dashboard.mockBanner.title")}
          description={t("dashboard.mockBanner.description")}
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic
              title={t("dashboard.kpis.totalAssets")}
              value={kpis.total_assets}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t("dashboard.kpis.totalAssetsHint")}
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title={t("dashboard.kpis.inStock")} value={kpis.in_stock_assets} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title={t("dashboard.kpis.inUse")} value={kpis.in_use_assets} />
            <Progress percent={Math.round(inUseRatio)} size="small" showInfo={false} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic
              title={t("dashboard.kpis.pendingRepair")}
              value={kpis.pending_repair_assets}
              valueStyle={{ color: kpis.pending_repair_assets > 0 ? "#d48806" : undefined }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic
              title={t("dashboard.kpis.underRepair")}
              value={kpis.under_repair_assets}
              valueStyle={{ color: kpis.under_repair_assets > 0 ? "#cf1322" : undefined }}
            />
            <Progress
              percent={Math.round(underRepairRatio)}
              size="small"
              showInfo={false}
              status={kpis.under_repair_assets > 0 ? "exception" : "normal"}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic
              title={t("dashboard.kpis.pendingReview")}
              value={kpis.pending_repair_requests}
              valueStyle={{ color: kpis.pending_repair_requests > 0 ? "#d48806" : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title={t("dashboard.categories.title")}>
            {asset_categories.length === 0 ? (
              <Empty description={t("dashboard.categories.empty")} />
            ) : (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                {asset_categories.map((row) => {
                  const percent =
                    maxCategoryCount > 0 ? Math.round((row.count / maxCategoryCount) * 100) : 0;
                  return (
                    <div key={row.category}>
                      <Row justify="space-between" style={{ marginBottom: 4 }}>
                        <Typography.Text>{row.category}</Typography.Text>
                        <Typography.Text strong>{row.count}</Typography.Text>
                      </Row>
                      <Progress percent={percent} showInfo={false} />
                    </div>
                  );
                })}
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title={t("dashboard.repairSummary.title")}>
            <Row gutter={[16, 16]}>
              <Col xs={12}>
                <Statistic
                  title={t("dashboard.repairSummary.createdToday")}
                  value={repair_summary.created_today}
                />
              </Col>
              <Col xs={12}>
                <Statistic
                  title={t("dashboard.repairSummary.pendingReview")}
                  value={repair_summary.pending_review}
                />
              </Col>
              <Col xs={12}>
                <Statistic
                  title={t("dashboard.repairSummary.underRepair")}
                  value={repair_summary.under_repair}
                />
              </Col>
              <Col xs={12}>
                <Statistic
                  title={t("dashboard.repairSummary.completedToday")}
                  value={repair_summary.completed_today}
                />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      <Card
        title={t("dashboard.recentPending.title")}
        extra={
          <Button type="link" onClick={() => navigate("/reviews?status=pending_review")}>
            {t("dashboard.recentPending.viewAll")}
          </Button>
        }
      >
        {recent_pending_repairs.length === 0 ? (
          <Empty description={t("dashboard.recentPending.empty")} />
        ) : (
          <List
            itemLayout="horizontal"
            dataSource={recent_pending_repairs}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/reviews/${item.id}`)}
              >
                <List.Item.Meta
                  title={
                    <Space size={8} wrap>
                      <Typography.Text strong>{item.repair_id}</Typography.Text>
                      <Tag color="gold">{t("dashboard.kpis.pendingReview")}</Tag>
                    </Space>
                  }
                  description={
                    <Space size={16} wrap>
                      <span>
                        {t("dashboard.recentPending.asset")}: {item.asset_name}
                      </span>
                      <span>
                        {t("dashboard.recentPending.requester")}: {item.requester_name}
                      </span>
                      <span>
                        {t("dashboard.recentPending.submittedAt")}:{" "}
                        {formatDateTime(item.created_at)}
                      </span>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </Space>
  );
};

export default Dashboard;
