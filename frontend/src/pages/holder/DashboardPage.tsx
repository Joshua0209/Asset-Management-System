import { Typography } from 'antd';

const { Title } = Typography;

export function HolderDashboardPage() {
  return (
    <div>
      <Title level={3}>My Dashboard</Title>
      <p>Your assigned assets and repair requests will appear here.</p>
    </div>
  );
}
