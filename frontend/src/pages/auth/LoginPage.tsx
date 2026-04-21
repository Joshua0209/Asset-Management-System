import { Button, Card, Form, Input, Typography, Space, App } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { authApi } from '@/api/endpoints/auth';
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher';
import { colors } from '@/styles/tokens';

const { Title, Text } = Typography;

export function LoginPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const setAuth = useAuthStore((s) => s.setAuth);
  const { message } = App.useApp();

  const onFinish = async (values: { email: string; password: string }) => {
    try {
      const res = await authApi.login(values);
      const { access_token, user } = res.data.data;
      setAuth(user, access_token);
      navigate(user.role === 'manager' ? '/manager' : '/holder');
    } catch {
      message.error(t('login.loginFailed'));
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: colors.neutral[50],
        position: 'relative',
      }}
    >
      <div style={{ position: 'absolute', top: 24, right: 24 }}>
        <LanguageSwitcher />
      </div>

      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
        <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
          <div>
            <Title level={3} style={{ margin: 0, color: colors.brand.primary }}>
              {t('login.title')}
            </Title>
            <Text type="secondary">{t('login.subtitle')}</Text>
          </div>

          <Form layout="vertical" onFinish={onFinish} autoComplete="off">
            <Form.Item
              name="email"
              rules={[
                { required: true, message: t('login.emailRequired') },
                { type: 'email', message: t('login.emailInvalid') },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder={t('login.emailPlaceholder')} size="large" />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: t('login.passwordRequired') }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder={t('login.passwordPlaceholder')} size="large" />
            </Form.Item>

            <Form.Item>
              <Button type="primary" htmlType="submit" size="large" block>
                {t('login.loginButton')}
              </Button>
            </Form.Item>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
