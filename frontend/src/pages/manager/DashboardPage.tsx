import { Typography } from 'antd';

const { Title } = Typography;

export function ManagerDashboardPage() {
  return (
    <div>
      <Title level={3}>Manager Dashboard</Title>
      <p>Asset overview and pending actions will appear here.</p>
    </div>
  );
}
