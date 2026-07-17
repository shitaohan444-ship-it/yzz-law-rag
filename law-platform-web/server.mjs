import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer, request as proxyRequest } from 'node:http';
import { extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const port = Number(process.env.PORT ?? 8080);
const apiTarget = new URL(process.env.API_TARGET ?? 'http://platform-api:3000');
const distDir = fileURLToPath(new URL('./dist/', import.meta.url));
const indexPath = resolve(distDir, 'index.html');

const mimeTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.map', 'application/json; charset=utf-8'],
  ['.png', 'image/png'],
  ['.svg', 'image/svg+xml'],
  ['.webp', 'image/webp'],
  ['.woff2', 'font/woff2'],
]);

function proxyApi(req, res) {
  const headers = {};
  for (const name of ['accept', 'accept-language', 'content-length', 'content-type', 'user-agent']) {
    if (req.headers[name] !== undefined) headers[name] = req.headers[name];
  }
  headers.host = apiTarget.host;
  headers['x-forwarded-for'] = req.socket.remoteAddress ?? '';
  headers['x-forwarded-proto'] = 'http';

  const upstream = proxyRequest(
    {
      protocol: apiTarget.protocol,
      hostname: apiTarget.hostname,
      port: apiTarget.port,
      method: req.method,
      path: req.url,
      headers,
      timeout: 900_000,
    },
    (upstreamResponse) => {
      res.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(res);
    },
  );

  upstream.on('timeout', () => upstream.destroy(new Error('upstream timeout')));
  upstream.on('error', () => {
    if (res.headersSent) return res.destroy();
    res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: { code: 'UPSTREAM_UNAVAILABLE', message: '平台服务暂时不可用' } }));
  });
  req.on('aborted', () => upstream.destroy());
  req.pipe(upstream);
}

function serveFile(req, res) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url ?? '/', 'http://localhost').pathname);
  } catch {
    res.writeHead(400).end('Bad Request');
    return;
  }

  const requestedPath = resolve(distDir, `.${pathname}`);
  const isSafePath = requestedPath.startsWith(distDir);
  const filePath =
    isSafePath && existsSync(requestedPath) && statSync(requestedPath).isFile()
      ? requestedPath
      : indexPath;
  const contentType = mimeTypes.get(extname(filePath).toLowerCase()) ?? 'application/octet-stream';
  const cacheControl = filePath === indexPath ? 'no-cache' : 'public, max-age=31536000, immutable';

  res.writeHead(200, {
    'content-type': contentType,
    'cache-control': cacheControl,
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'SAMEORIGIN',
    'referrer-policy': 'same-origin',
  });
  if (req.method === 'HEAD') return res.end();
  createReadStream(filePath).pipe(res);
}

createServer((req, res) => {
  if ((req.url ?? '').startsWith('/api/')) return proxyApi(req, res);
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { allow: 'GET, HEAD' }).end('Method Not Allowed');
    return;
  }
  serveFile(req, res);
}).listen(port, '0.0.0.0', () => {
  console.log(`law-platform-web listening on 0.0.0.0:${port}`);
});
