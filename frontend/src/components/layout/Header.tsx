import { Layout, Space, Button, Typography } from 'antd';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { layout } from '@/styles/tokens';

const { Header } = Layout;
const { Text } = Typography;

export function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Header
      style={{
        height: layout.headerHeight,
        lineHeight: `${layout.headerHeight}px`,
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        borderBottom: '1px solid #f0f0f0',
      }}
    >
      <Space>
        {user && (
          <Space>
            <UserOutlined />
            <Text>{user.name}</Text>
          </Space>
        )}
        <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout}>
          Logout
        </Button>
      </Space>
    </Header>
  );
}
