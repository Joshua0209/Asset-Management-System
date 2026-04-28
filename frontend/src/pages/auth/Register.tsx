import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Select, message } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, BankOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { RegisterRequest } from '../../api/types';
import { AxiosError } from 'axios';

const { Title, Text } = Typography;
const { Option } = Select;

const Register: React.FC = () => {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: RegisterRequest) => {
    setLoading(true);
    try {
      await register(values);
      message.success(t('auth.register.registerSuccess'));
      navigate('/auth/login');
    } catch (error) {
      const axiosError = error as AxiosError<{ error: { message: string } }>;
      message.error(axiosError.response?.data?.error?.message || t('errors.validationError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 64px)', padding: '20px 0' }}>
      <Card style={{ width: 450, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>{t('auth.register.title')}</Title>
          <Text type="secondary">{t('auth.register.subtitle')}</Text>
        </div>
        <Form
          name="register"
          onFinish={onFinish}
          layout="vertical"
          size="large"
          initialValues={{ role: 'holder' }}
        >
          <Form.Item
            name="name"
            label={t('auth.register.name')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('auth.register.name')} />
          </Form.Item>
          <Form.Item
            name="email"
            label={t('auth.register.email')}
            rules={[
              { required: true, message: t('validation.required') },
              { type: 'email', message: t('validation.emailInvalid') }
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder={t('auth.register.email')} />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('auth.register.password')}
            rules={[
              { required: true, message: t('validation.required') },
              { min: 8, message: t('validation.passwordMinLength') },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
                message: t('validation.passwordPattern')
              }
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.register.password')} />
          </Form.Item>
          <Form.Item
            name="department"
            label={t('auth.register.department')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input prefix={<BankOutlined />} placeholder={t('auth.register.department')} />
          </Form.Item>
          <Form.Item
            name="role"
            label={t('auth.register.role')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Select placeholder={t('auth.register.role')}>
              <Option value="holder">{t('auth.register.roleHolder')}</Option>
              <Option value="manager">{t('auth.register.roleManager')}</Option>
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('common.button.register')}
            </Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">{t('auth.register.hasAccount')} </Text>
            <Link to="/auth/login">{t('common.button.login')}</Link>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default Register;
