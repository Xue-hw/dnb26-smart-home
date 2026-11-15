import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const distRoot = resolve(projectRoot, 'dist');
const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml; charset=utf-8',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

async function fileInfo(path) {
  try {
    return await stat(path);
  } catch {
    return null;
  }
}

async function handleRequest(request, response) {
  try {
    const url = new URL(request.url || '/', 'http://127.0.0.1');
    const pathname = decodeURIComponent(url.pathname);
    const relativePath = pathname.replace(/^[/\\]+/, '');
    let filePath = resolve(distRoot, relativePath);
    if (filePath !== distRoot && !filePath.startsWith(`${distRoot}${sep}`)) {
      response.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Forbidden');
      return;
    }

    let info = await fileInfo(filePath);
    if (info?.isDirectory()) {
      filePath = resolve(filePath, 'index.html');
      info = await fileInfo(filePath);
    }
    if (!info?.isFile()) {
      if (extname(pathname)) {
        response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        response.end('Not Found');
        return;
      }
      filePath = resolve(distRoot, 'index.html');
      info = await fileInfo(filePath);
    }
    if (!info?.isFile()) {
      response.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('dist/index.html not found. Run npm run build first.');
      return;
    }

    response.writeHead(200, {
      'Content-Type': mimeTypes[extname(filePath).toLowerCase()] || 'application/octet-stream',
      'Content-Length': info.size,
      'Cache-Control': 'no-cache',
      'X-Content-Type-Options': 'nosniff',
    });
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    const stream = createReadStream(filePath);
    stream.on('error', () => response.destroy());
    stream.pipe(response);
  } catch {
    response.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Bad Request');
  }
}

async function listen(port) {
  return new Promise((resolvePromise, rejectPromise) => {
    const server = createServer((request, response) => {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        response.writeHead(405, { Allow: 'GET, HEAD' });
        response.end();
        return;
      }
      void handleRequest(request, response);
    });
    server.once('error', (error) => {
      if (error.code === 'EADDRINUSE' && port < 4193) {
        resolvePromise(listen(port + 1));
      } else {
        rejectPromise(error);
      }
    });
    server.listen(port, '127.0.0.1', () => resolvePromise(server));
  });
}

const initialInfo = await fileInfo(resolve(distRoot, 'index.html'));
if (!initialInfo?.isFile()) {
  console.error('未找到 dist/index.html，请先运行 npm run build。');
  process.exit(1);
}

const server = await listen(4173);
const address = server.address();
const port = typeof address === 'object' && address ? address.port : 4173;
const previewUrl = `http://127.0.0.1:${port}/`;
console.log('');
console.log('DnB26 智能家居 GUI 本地预览已启动');
console.log(`预览地址：${previewUrl}`);
console.log('数据模式：Mock 本地演示，不需要后端');
console.log('关闭此窗口或按 Ctrl+C 即可停止预览。');
console.log('');

if (!process.argv.includes('--no-open') && process.env.DNB26_PREVIEW_NO_OPEN !== '1') {
  const command = process.platform === 'win32' ? 'cmd' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  const args = process.platform === 'win32' ? ['/c', 'start', '', previewUrl] : [previewUrl];
  const browser = spawn(command, args, { detached: true, stdio: 'ignore' });
  browser.on('error', () => console.log('请在浏览器手动打开上述预览地址。'));
  browser.unref();
}

process.on('SIGINT', () => server.close(() => process.exit(0)));
process.on('SIGTERM', () => server.close(() => process.exit(0)));
