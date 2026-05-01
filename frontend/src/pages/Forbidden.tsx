import React from "react";
import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

const Forbidden: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Result
      status="403"
      title={t("errors.forbiddenTitle")}
      subTitle={t("errors.forbidden")}
      extra={
        <Button type="primary" onClick={() => navigate("/", { replace: true })}>
          {t("errors.backHome")}
        </Button>
      }
    />
  );
};

export default Forbidden;
