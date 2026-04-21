import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

export function ManagerAssetListPage() {
  const { t } = useTranslation();

  return (
    <div>
      <Title level={3}>{t('assetList.title')}</Title>
      <p>{t('assetList.description')}</p>
    </div>
  );
}
