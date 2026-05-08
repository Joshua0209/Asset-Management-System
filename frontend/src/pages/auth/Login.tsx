import React, { useState } from "react";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { ApiError } from "../../api";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";

interface LocationState {
  from?: string;
}

interface LoginFormValues {
  email: string;
  password: string;
}

const Login: React.FC = () => {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFinish = async (values: LoginFormValues) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(values.email, values.password);
      const dest = (location.state as LocationState | null)?.from ?? "/";
      navigate(dest, { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError(t("errors.serverError"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <Card style={{ width: 400, maxWidth: "100%" }}>
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {t("auth.login.title")}
            </Typography.Title>
            <LanguageSwitcher />
          </div>
          {error && <Alert type="error" title={error} showIcon role="alert" />}
          <Form<LoginFormValues> layout="vertical" onFinish={handleFinish} disabled={submitting}>
            <Form.Item
              label={t("auth.login.email")}
              name="email"
              rules={[
                { required: true, message: t("validation.required") },
                { type: "email", message: t("validation.emailInvalid") },
              ]}
            >
              <Input autoComplete="email" />
            </Form.Item>
            <Form.Item
              label={t("auth.login.password")}
              name="password"
              rules={[{ required: true, message: t("validation.required") }]}
            >
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={submitting} block>
                {t("auth.login.submit")}
              </Button>
            </Form.Item>
          </Form>
          <Typography.Text>
            {t("auth.login.noAccount")} <Link to="/auth/register">{t("auth.login.register")}</Link>
          </Typography.Text>
        </Space>
      </Card>
    </div>
  );
};

export default Login;
