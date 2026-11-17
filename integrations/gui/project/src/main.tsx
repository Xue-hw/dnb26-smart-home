import { Capacitor } from '@capacitor/core';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AppDataProvider } from '@/context/AppDataContext';
import './styles.css';
import './atlas-theme.css';
import { restoreAdminSession } from '@/services/connection';

async function start() {
  let warning = '';
  try { await restoreAdminSession(); }
  catch { warning = '无法恢复管理员权限，请在系统页重新授权。状态查看仍可使用。'; }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>{warning && <p role="alert">{warning}</p>}<BrowserRouter><AppDataProvider><App /></AppDataProvider></BrowserRouter></StrictMode>,
  );
}
void start();

if (!Capacitor.isNativePlatform() && import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => { void navigator.serviceWorker.register('/sw.js').catch(() => { /* The web UI remains usable without offline help. */ }); });
}
