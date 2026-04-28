import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { LoginRequest } from '../../api/types';
import { AxiosError } from 'axios';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: LoginRequest) => {
    setLoading(true);
    try {
      await login(values);
      message.success(t('auth.login.loginSuccess'));
      navigate('/dashboard');
    } catch (error) {
      const axiosError = error as AxiosError<{ error: { message: string } }>;
      message.error(axiosError.response?.data?.error?.message || t('errors.loginFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 64px)' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>{t('auth.login.title')}</Title>
          <Text type="secondary">{t('auth.login.subtitle')}</Text>
        </div>
        <Form
          name="login"
          initialValues={{ remember: true }}
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: t('validation.required') },
              { type: 'email', message: t('validation.emailInvalid') }
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('auth.login.email')} />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.login.password')} />
          </Form.Item>
          <div style={{ marginBottom: 24, textAlign: 'right' }}>
            <Link to="/auth/password-reset">{t('auth.login.forgotPassword')}</Link>
          </div>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('common.button.login')}
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">{t('auth.login.noAccount')} </Text>
            <Link to="/auth/register">{t('common.button.register')}</Link>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default Login;
