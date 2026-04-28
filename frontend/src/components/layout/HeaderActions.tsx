import React from 'react';
import { Button } from 'antd';
import { SunOutlined, MoonOutlined } from '@ant-design/icons';
import { LanguageSwitcher } from '../LanguageSwitcher';
import { useTheme } from '../../contexts/ThemeContext';

export const HeaderActions: React.FC = () => {
  const { isDarkMode, toggleTheme } = useTheme();

  return (
    <>
      <Button
        type="text"
        icon={isDarkMode ? <SunOutlined /> : <MoonOutlined />}
        onClick={toggleTheme}
        style={{ fontSize: '16px' }}
      />
      <LanguageSwitcher />
    </>
  );
};
