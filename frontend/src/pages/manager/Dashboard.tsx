import React from "react";
import { Card, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";

const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  return (
    <Space orientation="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t("common.nav.dashboard")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t("dashboard.description")}
      </Typography.Paragraph>
      <Card>
        <Typography.Text type="secondary">{t("dashboard.demoNotice")}</Typography.Text>
      </Card>
    </Space>
  );
};

export default Dashboard;
