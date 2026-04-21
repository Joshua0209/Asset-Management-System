import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { DashboardOutlined, LaptopOutlined, HomeOutlined, ToolOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { UserRole } from '@/types/user';
import { layout } from '@/styles/tokens';

const { Sider } = Layout;

interface SidebarProps {
  role: UserRole;
}

export function Sidebar({ role }: SidebarProps) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const managerMenuItems = [
    {
      key: '/manager/dashboard',
      icon: <DashboardOutlined />,
      label: t('sidebar.managerDashboard'),
    },
    {
      key: '/manager/assets',
      icon: <LaptopOutlined />,
      label: t('sidebar.assetManagement'),
    },
  ];

  const holderMenuItems = [
    {
      key: '/holder/dashboard',
      icon: <HomeOutlined />,
      label: t('sidebar.myDashboard'),
    },
  ];

  const menuItems = role === 'manager' ? managerMenuItems : holderMenuItems;

  return (
    <Sider
      collapsible
      collapsed={collapsed}
      onCollapse={setCollapsed}
      width={layout.sidebarWidth}
      collapsedWidth={layout.sidebarCollapsedWidth}
      style={{
        overflow: 'auto',
        height: '100vh',
        position: 'sticky',
        top: 0,
        left: 0,
      }}
    >
      <div
        style={{
          height: layout.headerHeight,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: '1px solid #f0f0f0',
        }}
      >
        <ToolOutlined style={{ fontSize: 24, color: '#C8102E' }} />
        {!collapsed && (
          <span
            style={{
              marginLeft: 8,
              fontSize: 16,
              fontWeight: 600,
              color: '#212529',
              whiteSpace: 'nowrap',
            }}
          >
            AMS
          </span>
        )}
      </div>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        style={{ borderRight: 0, marginTop: 8 }}
      />
    </Sider>
  );
}
