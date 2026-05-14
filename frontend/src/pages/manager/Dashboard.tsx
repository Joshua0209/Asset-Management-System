import React from "react";
import { Typography } from "antd";
import { useTranslation } from "react-i18next";

const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  return (
    <div>
      <Typography.Title level={2}>{t("common.nav.dashboard")}</Typography.Title>
      <p>Welcome to the Asset Management System Dashboard.</p>
    </div>
  );
};

export default Dashboard;
