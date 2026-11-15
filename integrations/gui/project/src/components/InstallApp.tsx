import { Capacitor } from '@capacitor/core';
import { useEffect, useState } from 'react';
import { Download, Smartphone } from 'lucide-react';
import { Modal } from './Common';
interface InstallPrompt extends Event { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }>; }
export function InstallApp() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [help, setHelp] = useState(false);
  const [message, setMessage] = useState('');
  const [installed, setInstalled] = useState(false);
  useEffect(() => {
    setInstalled(Boolean(window.matchMedia?.('(display-mode: standalone)').matches));
    const ready = (e: Event) => { e.preventDefault(); setPrompt(e as InstallPrompt); };
    const done = () => { setInstalled(true); setPrompt(null); };
    window.addEventListener('beforeinstallprompt', ready);
    window.addEventListener('appinstalled', done);
    return () => { window.removeEventListener('beforeinstallprompt', ready); window.removeEventListener('appinstalled', done); };
  }, []);
  async function install() {
    if (!prompt) { setHelp(true); return; }
    try { await prompt.prompt(); const result = await prompt.userChoice; setMessage(result.outcome === 'accepted' ? '安装请求已接受，请查看系统提示。' : '已取消安装，你仍可通过网页使用。'); }
    catch { setMessage('暂时无法安装，请尝试浏览器菜单中的安装选项。'); }
    finally { setPrompt(null); setHelp(true); }
  }
  if (Capacitor.isNativePlatform()) return <span className="native-label">Android · 演示版</span>;
  return <><button className="install-button" onClick={() => void install()}><Smartphone size={18} />{installed ? '已在 App 模式' : prompt ? '安装应用' : '手机使用'}</button>{help && <Modal title="把家居面板放到主屏幕" description="电脑和手机共用同一套网页界面。" onClose={() => setHelp(false)}><div className="install-guide"><Download size={32} /><p>{message || '可安装的网页应用，让你从桌面图标直接打开控制面板。'}</p><ol><li>用手机打开部署后的网址。</li><li>Android Chrome：浏览器菜单 → 安装应用或添加到主屏幕。</li><li>iPhone Safari：分享 → 添加到主屏幕。</li></ol><p>安装需要 HTTPS 或本机 localhost，并取决于浏览器支持。普通局域网 HTTP 地址可浏览网页；部署为 HTTPS 后再验证安装。</p><p>断网时无法读取实时设备或执行控制。安装图标不会让后端自动运行。</p></div></Modal>}</>;
}
