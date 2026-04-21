import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

export function HolderDashboardPage() {
  const { t } = useTranslation();

  return (
    <div>
      <Title level={3}>{t('holderDashboard.title')}</Title>
      <p>{t('holderDashboard.description')}</p>
    </div>
  );
}
