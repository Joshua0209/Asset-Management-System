import React, { useEffect, useState } from 'react';
import { Typography, Form, Input, Select, Upload, Button, message, Card } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { RcFile, UploadFile } from 'antd/es/upload/interface';
import { ApiError, assetsApi, repairRequestsApi } from '../../api';
import type { AssetRecord } from '../../api/assets/types';
import { getApiErrorMessage } from '../../utils/apiErrors';

const { Title } = Typography;
const { TextArea } = Input;

const ELIGIBLE_ASSETS_PAGE_SIZE = 100;

const SubmitRepairRequest: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [assetsLoading, setAssetsLoading] = useState(true);
  const [assetsError, setAssetsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAssetsLoading(true);
    setAssetsError(null);
    assetsApi
      .listMyAssets({ status: 'in_use', perPage: ELIGIBLE_ASSETS_PAGE_SIZE })
      .then((response) => {
        if (cancelled) return;
        setAssets(response.data);
      })
      .catch((error) => {
        if (cancelled) return;
        const fallback = t('common.repairRequest.assetsLoadError');
        const messageText =
          error instanceof ApiError ? (error.message ?? fallback) : fallback;
        setAssetsError(messageText);
      })
      .finally(() => {
        if (cancelled) return;
        setAssetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

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
      await repairRequestsApi.submitRepairRequest(formData);
      message.success(t('common.repairRequest.successMessage'));
      navigate('/repairs');
    } catch (error) {
      if (error instanceof ApiError) {
        message.error(getApiErrorMessage(error, t));
      } else {
        console.error('Submission error:', error);
        message.error(t('common.repairRequest.errorMessage'));
      }
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
            help={assetsError ?? undefined}
            validateStatus={assetsError ? 'error' : undefined}
          >
            <Select
              placeholder={t('common.repairRequest.assetSelectPlaceholder')}
              loading={assetsLoading}
              disabled={assetsLoading || Boolean(assetsError)}
              showSearch
              optionFilterProp="label"
              notFoundContent={
                assetsLoading
                  ? t('common.repairRequest.assetsLoading')
                  : t('common.repairRequest.assetsEmpty')
              }
              options={assets.map((asset) => ({
                value: asset.id,
                label: `${asset.asset_code} — ${asset.name}`,
              }))}
            />
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
