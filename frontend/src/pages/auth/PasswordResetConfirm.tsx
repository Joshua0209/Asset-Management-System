import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { authApi } from '../../api/auth';
import { AxiosError } from 'axios';

const { Title, Text } = Typography;

const PasswordResetConfirm: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const token = searchParams.get('token');

  const onFinish = async (values: { password: string }) => {
    if (!token) {
      message.error('Invalid or missing token');
      return;
    }
    setLoading(true);
    try {
      await authApi.confirmPasswordReset({
        token,
        new_password: values.password
      });
      message.success(t('auth.passwordReset.confirmSuccess'));
      navigate('/auth/login');
    } catch (error) {
      const axiosError = error as AxiosError<{ error: { message: string } }>;
      message.error(axiosError.response?.data?.error?.message || t('errors.serverError'));
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 64px)' }}>
        <Card style={{ width: 400, textAlign: 'center' }}>
          <Title level={4} type="danger">Invalid Request</Title>
          <Text>Password reset token is missing. Please request a new link.</Text>
          <div style={{ marginTop: 24 }}>
            <Link to="/auth/password-reset">{t('auth.passwordReset.requestTitle')}</Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 64px)' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>{t('auth.passwordReset.confirmTitle')}</Title>
          <Text type="secondary">{t('auth.passwordReset.confirmSubtitle')}</Text>
        </div>
        <Form
          name="password_reset_confirm"
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="password"
            label={t('auth.passwordReset.newPassword')}
            rules={[
              { required: true, message: t('validation.required') },
              { min: 8, message: t('validation.passwordMinLength') },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
                message: t('validation.passwordPattern')
              }
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.passwordReset.newPassword')} />
          </Form.Item>
          <Form.Item
            name="confirm"
            label={t('auth.passwordReset.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('validation.required') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('validation.passwordMismatch')));
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.passwordReset.confirmPassword')} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('common.button.resetPassword')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default PasswordResetConfirm;
