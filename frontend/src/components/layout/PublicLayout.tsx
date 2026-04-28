import React from 'react';
import { Layout, theme } from 'antd';
import { Outlet } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import { HeaderActions } from './HeaderActions';

const { Header, Content } = Layout;

const PublicLayout: React.FC = () => {
  const { isDarkMode } = useTheme();
  const {
    token: { colorBgContainer },
  } = theme.useToken();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{
        padding: '0 24px',
        background: colorBgContainer,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '16px'
      }}>
        <HeaderActions />
      </Header>
      <Content style={{ background: isDarkMode ? '#141414' : '#f0f2f5' }}>
        <Outlet />
      </Content>
    </Layout>
  );
};

export default PublicLayout;
