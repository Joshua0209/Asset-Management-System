import { Button, Dropdown } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { MenuProps } from 'antd';

export function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const items: MenuProps['items'] = [
    {
      key: 'en',
      label: 'English',
    },
    {
      key: 'zh-TW',
      label: '繁體中文',
    },
  ];

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    i18n.changeLanguage(key);
  };

  return (
    <Dropdown menu={{ items, onClick: handleMenuClick }} placement="bottomRight">
      <Button type="text" icon={<GlobalOutlined />}>
        {i18n.language === 'en' ? 'English' : '繁體中文'}
      </Button>
    </Dropdown>
  );
}
