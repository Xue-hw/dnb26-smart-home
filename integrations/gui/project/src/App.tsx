import { lazy, Suspense, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { LoadingBlock } from '@/components/Common';

const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const MonitorPage = lazy(() => import('@/pages/MonitorPage'));
const HistoryPage = lazy(() => import('@/pages/HistoryPage'));
const PersonnelPage = lazy(() => import('@/pages/PersonnelPage'));
const SystemPage = lazy(() => import('@/pages/SystemPage'));
const InterfacePage = lazy(() => import('@/pages/InterfacePage'));

function screen(node: ReactNode) {
  return <Suspense fallback={<LoadingBlock label="正在加载页面模块…" />}>{node}</Suspense>;
}

export default function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={screen(<DashboardPage />)} />
    <Route path="monitor" element={screen(<MonitorPage />)} />
    <Route path="history" element={screen(<HistoryPage />)} />
    <Route path="personnel" element={screen(<PersonnelPage />)} />
    <Route path="system" element={screen(<SystemPage />)} />
    <Route path="interfaces" element={screen(<InterfacePage />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Route></Routes>;
}
