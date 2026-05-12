import React, { useState } from "react";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthContext";
import { ApiError, authApi } from "../../api";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";

interface RegisterFormValues {
  name: string;
  department: string;
  email: string;
  password: string;
}

const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_POLICY_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/;

const Register: React.FC = () => {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFinish = async (values: RegisterFormValues) => {
    setError(null);
    setSubmitting(true);
    try {
      await authApi.register(values);
      await login(values.email, values.password);
      navigate("/", { replace: true });
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
      <Card style={{ width: 480, maxWidth: "100%" }}>
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              {t("auth.register.title")}
            </Typography.Title>
            <LanguageSwitcher />
          </div>
          {error && <Alert type="error" title={error} showIcon role="alert" />}
          <Form<RegisterFormValues> layout="vertical" onFinish={handleFinish} disabled={submitting}>
            <Form.Item
              label={t("auth.register.name")}
              name="name"
              rules={[{ required: true, message: t("validation.required") }]}
            >
              <Input autoComplete="name" />
            </Form.Item>
            <Form.Item
              label={t("auth.register.department")}
              name="department"
              rules={[{ required: true, message: t("validation.required") }]}
            >
              <Input autoComplete="organization" />
            </Form.Item>
            <Form.Item
              label={t("auth.register.email")}
              name="email"
              rules={[
                { required: true, message: t("validation.required") },
                { type: "email", message: t("validation.emailInvalid") },
              ]}
            >
              <Input autoComplete="email" />
            </Form.Item>
            <Form.Item
              label={t("auth.register.password")}
              name="password"
              extra={t("auth.register.passwordPolicy")}
              rules={[
                { required: true, message: t("validation.required") },
                { min: PASSWORD_MIN_LENGTH, message: t("auth.register.passwordPolicy") },
                {
                  pattern: PASSWORD_POLICY_PATTERN,
                  message: t("auth.register.passwordPolicy"),
                },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={submitting} block>
                {t("auth.register.submit")}
              </Button>
            </Form.Item>
          </Form>
          <Typography.Text>
            {t("auth.register.haveAccount")} <Link to="/auth/login">{t("auth.register.login")}</Link>
          </Typography.Text>
        </Space>
      </Card>
    </div>
  );
};

export default Register;
