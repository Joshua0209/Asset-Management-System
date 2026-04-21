import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';

const { Title } = Typography;

export function ManagerDashboardPage() {
  const { t } = useTranslation();

  return (
    <div>
      <Title level={3}>{t('managerDashboard.title')}</Title>
      <p>{t('managerDashboard.description')}</p>
    </div>
  );
}
