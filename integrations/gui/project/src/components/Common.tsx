import { useEffect, useRef, type ReactNode } from 'react';
import { useAppData } from '@/context/AppDataContext';
import { AlertCircle, Database, Info, LoaderCircle, RefreshCw, X } from 'lucide-react';

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>;
}

export function Panel({ title, description, icon, actions, children, className = '' }: { title: string; description?: string; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-header"><div className="panel-heading">{icon && <span className="panel-icon">{icon}</span>}<div><h2>{title}</h2>{description && <p>{description}</p>}</div></div>{actions}</div><div className="panel-body">{children}</div></section>;
}

export function StatusBadge({ tone = 'neutral', children }: { tone?: 'success' | 'danger' | 'warning' | 'info' | 'neutral'; children: ReactNode }) {
  return <span className={`status-badge ${tone}`}><span className="status-dot" />{children}</span>;
}

export function DemoNotice({ children = '当前为纯前端演示，数据来自浏览器本地 Mock 数据库。' }: { children?: ReactNode }) {
  const { mode } = useAppData();
  if (mode !== 'mock') return null;
  return <div className="demo-notice"><Database size={17} /><div>{children}</div></div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><Info size={28} /><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state"><AlertCircle size={20} /><span>{message}</span>{retry && <button className="button secondary small" onClick={retry}><RefreshCw size={14} />重试</button>}</div>;
}

export function LoadingBlock({ label = '正在读取数据…' }: { label?: string }) {
  return <div className="loading-block"><LoaderCircle className="spin" size={22} /><span>{label}</span></div>;
}

export function Modal({ title, description, children, onClose }: { title: string; description?: string; children: ReactNode; onClose: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    if (!dialog.current?.contains(document.activeElement)) dialog.current?.querySelector<HTMLElement>('input, button')?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current();
      if (event.key === 'Tab') {
        const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]') || []);
        if (!nodes.length) return;
        if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0].focus(); }
      }
    };
    document.addEventListener('keydown', handler);
    return () => { document.removeEventListener('keydown', handler); previous?.focus(); };
  }, []);
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="modal-header"><div><h2>{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" onClick={onClose} aria-label="关闭弹窗"><X size={20} /></button></div>{children}</div></div>;
}
