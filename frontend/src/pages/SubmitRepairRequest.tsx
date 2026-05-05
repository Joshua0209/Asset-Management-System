import React, { useState } from 'react';
import { Typography, Form, Input, Upload, Button, message, Card } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { RcFile, UploadFile } from 'antd/es/upload/interface';
import { API_BASE } from '../api';

const { Title } = Typography;
const { TextArea } = Input;

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
  };
}

const SubmitRepairRequest: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const getErrorMessageByCode = (code?: string, fallbackMessage?: string) => {
    switch (code) {
      case 'unauthorized':
        return t('errors.unauthorized');
      case 'forbidden':
        return t('errors.forbidden');
      case 'not_found':
        return t('errors.notFound');
      case 'conflict':
        return t('errors.conflict');
      case 'duplicate_request':
        return t('errors.duplicateRequest');
      case 'invalid_transition':
        return t('errors.invalidTransition');
      case 'validation_error':
        return t('errors.validationError');
      case 'payload_too_large':
        return t('errors.payloadTooLarge');
      case 'unsupported_media_type':
        return t('errors.unsupportedMediaType');
      case 'rate_limit_exceeded':
        return t('errors.rateLimitExceeded');
      default:
        return fallbackMessage || t('common.repairRequest.errorMessage');
    }
  };

  const onFinish = async (values: { asset_id: string; fault_description: string }) => {
    setSubmitting(true);
    const formData = new FormData();
    formData.append('asset_id', values.asset_id);
    formData.append('fault_description', values.fault_description);

    fileList.forEach((file) => {
      if (file.originFileObj) {
        formData.append('images', file.originFileObj);
      }
    });

    try {
      const response = await fetch(`${API_BASE}/repair-requests`, {
        method: 'POST',
        headers: {
          // Note: Content-Type is handled automatically by fetch for FormData
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: formData,
      });

      if (response.ok) {
        message.success(t('common.repairRequest.successMessage'));
        navigate('/reviews'); // Or wherever it makes sense to go after
      } else {
        let errorData: ErrorEnvelope | null = null;
        try {
          errorData = (await response.json()) as ErrorEnvelope;
        } catch {
          // Non-JSON responses (e.g., proxy misroutes) still surface a friendly fallback.
        }
        message.error(
          getErrorMessageByCode(errorData?.error?.code, errorData?.error?.message),
        );
      }
    } catch (error) {
      console.error('Submission error:', error);
      message.error(t('common.repairRequest.errorMessage'));
    } finally {
      setSubmitting(false);
    }
  };

  const beforeUpload = (file: RcFile) => {
    const isJpgOrPng = file.type === 'image/jpeg' || file.type === 'image/png';
    if (!isJpgOrPng) {
      message.error(t('common.repairRequest.uploadFormat'));
      return Upload.LIST_IGNORE;
    }
    const isLt5M = file.size / 1024 / 1024 < 5;
    if (!isLt5M) {
      message.error(t('common.repairRequest.uploadSize'));
      return Upload.LIST_IGNORE;
    }
    return false; // Prevent automatic upload
  };

  const handleFileChange = ({ fileList: newFileList }: { fileList: UploadFile[] }) => {
    setFileList(newFileList);
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <Title level={2}>{t('common.repairRequest.title')}</Title>
      <Card>
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ asset_id: '', fault_description: '' }}
        >
          <Form.Item
            name="asset_id"
            label={t('common.repairRequest.assetId')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input placeholder={t('common.repairRequest.assetId')} />
          </Form.Item>

          <Form.Item
            name="fault_description"
            label={t('common.repairRequest.faultDescription')}
            rules={[
              { required: true, message: t('validation.required') },
              { max: 1000, message: t('validation.maxLength') }
            ]}
          >
            <TextArea
              rows={4}
              placeholder={t('common.repairRequest.faultDescription')}
              maxLength={1000}
              showCount
            />
          </Form.Item>

          <Form.Item
            label={t('common.repairRequest.uploadImages')}
            extra={`${t('common.repairRequest.uploadLimit')}, ${t('common.repairRequest.uploadFormat')}, ${t('common.repairRequest.uploadSize')}`}
          >
            <Upload
              listType="picture"
              fileList={fileList}
              beforeUpload={beforeUpload}
              onChange={handleFileChange}
              maxCount={5}
              multiple
            >
              <Button icon={<UploadOutlined />}>{t('common.repairRequest.uploadImages')}</Button>
            </Upload>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              {t('common.repairRequest.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default SubmitRepairRequest;
