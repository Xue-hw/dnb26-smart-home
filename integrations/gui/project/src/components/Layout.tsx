import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import { useEffect, useState } from 'react';
import { formatDateTime } from '@/utils';
import { NavLink, Outlet } from 'react-router-dom';
import { Activity, BarChart3, FlaskConical, Home, LayoutDashboard, ScanSearch, Users } from 'lucide-react';
import { useAppData } from '@/context/AppDataContext';
import { InstallApp } from './InstallApp';
import { StatusBadge } from './Common';

const navItems = [
  { to: '/', label: '首页仪表盘', short: '首页', icon: LayoutDashboard },
  { to: '/monitor', label: '监控与识别', short: '识别', icon: ScanSearch },
  { to: '/history', label: '历史数据与统计', short: '历史', icon: BarChart3 },
  { to: '/personnel', label: '授权人员管理', short: '人员', icon: Users },
  { to: '/interfaces', label: '接口测试', short: '接口', icon: FlaskConical },
];

export function Layout() {
  const { status, mode, connectionError, lastSuccess, snapshot } = useAppData();
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => { const update = () => setOnline(navigator.onLine); window.addEventListener('online', update); window.addEventListener('offline', update); return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); }; }, []);
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    const listener = App.addListener('backButton', () => {
      const close = document.querySelector<HTMLButtonElement>('[role=dialog] button[aria-label=关闭弹窗]');
      if (close) close.click();
      else if (window.location.pathname !== '/') window.history.back();
      else void App.minimizeApp();
    });
    return () => { void listener.then(handle => handle.remove()); };
  }, []);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 10000); return () => clearInterval(timer); }, []);
  const stale = (mode === 'http' && !online) || Boolean(connectionError) || (lastSuccess > 0 && now - lastSuccess > 65000) || snapshot?.freshness === 'cached';
  return <div className="app-shell">
    <header className="topbar"><div className="topbar-inner">
      <NavLink to="/" className="brand"><span className="brand-mark"><Home size={20} /></span><span><strong>Nest / 智慧家</strong><small>DnB26 SMART LIVING</small></span></NavLink>
      <nav className="desktop-nav" aria-label="主导航">{navItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={16} />{label}</NavLink>)}</nav>
      <div className="sidebar-caption">我的家居空间</div><InstallApp /><div className="header-status"><StatusBadge tone={stale ? 'warning' : mode === 'mock' ? 'info' : status?.backend === 'online' ? 'success' : 'warning'}>{!online ? '网络已断开' : mode === 'mock' ? '演示模式' : stale ? '连接异常' : status?.backend === 'online' ? '设备连接模式' : '等待连接'}</StatusBadge></div>
    </div><nav className="mobile-nav" aria-label="移动端导航">{navItems.map(({ to, short, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => isActive ? 'mobile-link active' : 'mobile-link'}><Icon size={18} /><span>{short}</span></NavLink>)}</nav></header>
    <main className="main-content">{stale && <div className="error-state" role="alert">数据连接异常或已过期。以下保留上次读数，请勿视为实时状态。最后同步：{lastSuccess ? formatDateTime(new Date(lastSuccess).toISOString()) : '尚未成功'} {connectionError}</div>}<Outlet /></main>
    <footer className="footer"><div><Activity size={15} /><span>{status?.version || 'GUI v1.2.0'}</span><span className="footer-separator">·</span><span>{status?.model || '接口适配层已就绪'}</span></div><span>安全 · 舒适 · 清晰可控</span></footer>
  </div>;
}
