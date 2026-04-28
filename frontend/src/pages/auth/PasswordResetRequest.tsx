import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { authApi } from '../../api/auth';
import { AxiosError } from 'axios';

const { Title, Text } = Typography;

const PasswordResetRequest: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { email: string }) => {
    setLoading(true);
    try {
      await authApi.requestPasswordReset(values);
      message.success(t('auth.passwordReset.requestSuccess'));
      // In a real app, we might redirect to a "success" page or back to login
    } catch (error) {
      const axiosError = error as AxiosError<{ error: { message: string } }>;
      // Per API design, we always return 202 Accepted, but if something really fails (e.g. network)
      message.error(axiosError.response?.data?.error?.message || t('errors.serverError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 64px)' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>{t('auth.passwordReset.requestTitle')}</Title>
          <Text type="secondary">{t('auth.passwordReset.requestSubtitle')}</Text>
        </div>
        <Form
          name="password_reset_request"
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
            <Input prefix={<MailOutlined />} placeholder={t('auth.login.email')} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('common.button.sendResetLink')}
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            <Link to="/auth/login">{t('common.button.backToLogin')}</Link>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default PasswordResetRequest;
