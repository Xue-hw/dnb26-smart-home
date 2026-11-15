import { Capacitor } from '@capacitor/core';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AppDataProvider } from '@/context/AppDataContext';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode><BrowserRouter><AppDataProvider><App /></AppDataProvider></BrowserRouter></StrictMode>,
);

if (!Capacitor.isNativePlatform() && import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => { void navigator.serviceWorker.register('/sw.js').catch(() => { /* The web UI remains usable without offline help. */ }); });
}
