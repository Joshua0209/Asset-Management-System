import React, { useMemo, useState } from "react";
import { Avatar, Button, Dropdown, Layout, Menu, Space, Typography, theme } from "antd";
import type { MenuProps } from "antd";
import {
  AppstoreOutlined,
  CheckSquareOutlined,
  DashboardOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  SunOutlined,
  ToolOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { ParseKeys } from "i18next";
import { LanguageSwitcher } from "../LanguageSwitcher";
import { useAuth } from "../../auth/AuthContext";
import type { UserRole } from "../../api/auth";

const { Header, Sider, Content } = Layout;

interface MainLayoutProps {
  isDarkMode: boolean;
  toggleTheme: () => void;
}

interface NavItem {
  key: string;
  icon: React.ReactNode;
  labelKey: ParseKeys;
  roles: readonly UserRole[];
}

const NAV_ITEMS: readonly NavItem[] = [
  {
    key: "/dashboard",
    icon: <DashboardOutlined />,
    labelKey: "common.nav.dashboard",
    roles: ["manager"],
  },
  {
    key: "/assets",
    icon: <AppstoreOutlined />,
    labelKey: "common.nav.assets",
    roles: ["manager", "holder"],
  },
  {
    key: "/reviews",
    icon: <CheckSquareOutlined />,
    labelKey: "common.nav.reviews",
    roles: ["manager"],
  },
  {
    key: "/repairs/new",
    icon: <ToolOutlined />,
    labelKey: "common.nav.repairs",
    roles: ["holder"],
  },
];

const MainLayout: React.FC<MainLayoutProps> = ({ isDarkMode, toggleTheme }) => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const menuItems = useMemo(
    () =>
      NAV_ITEMS.filter((item) => (user ? item.roles.includes(user.role) : false)).map((item) => ({
        key: item.key,
        icon: item.icon,
        label: t(item.labelKey),
      })),
    [t, user],
  );

  const handleLogout = () => {
    logout();
    navigate("/auth/login", { replace: true });
  };

  const userMenu: MenuProps["items"] = [
    {
      key: "logout",
      icon: <LogoutOutlined />,
      label: t("common.nav.logout"),
      onClick: handleLogout,
    },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider trigger={null} collapsible collapsed={collapsed} theme={isDarkMode ? "dark" : "light"}>
        <div
          style={{
            height: 32,
            margin: 16,
            background: "rgba(0, 0, 0, 0.2)",
            borderRadius: 6,
          }}
        />
        <Menu
          theme={isDarkMode ? "dark" : "light"}
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: 0,
            background: colorBgContainer,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "expand sidebar" : "collapse sidebar"}
            style={{ fontSize: "16px", width: 64, height: 64 }}
          />
          <div style={{ paddingRight: 24, display: "flex", alignItems: "center", gap: 16 }}>
            <Button
              type="text"
              icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleTheme}
              aria-label={isDarkMode ? "switch to light mode" : "switch to dark mode"}
              style={{ fontSize: "16px" }}
            />
            <LanguageSwitcher />
            {user && (
              <Dropdown menu={{ items: userMenu }} placement="bottomRight" trigger={["click"]}>
                <Space style={{ cursor: "pointer" }}>
                  <Avatar size="small" icon={<UserOutlined />} />
                  <Typography.Text>{user.name}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t(`auth.role.${user.role}`)}
                  </Typography.Text>
                </Space>
              </Dropdown>
            )}
          </div>
        </Header>
        <Content
          style={{
            margin: "24px 16px",
            padding: 24,
            minHeight: 280,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
