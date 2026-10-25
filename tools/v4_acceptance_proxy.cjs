// Temporary staging-only same-origin bridge. No open proxy, app API or auth override.
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs');

function createProxy({ webTarget, socketTarget, site, publicOrigin }) {
  const external = new URL(publicOrigin);
  if (external.origin !== publicOrigin || !['http:', 'https:'].includes(external.protocol)) {
    throw new Error('Require one exact public HTTP(S) origin');
  }
  const options = (req, socket = false) => {
    const headers = { ...req.headers, 'x-frappe-site-name': site };
    if (socket) {
      if (req.headers.host?.toLowerCase() !== external.host ||
          ['cross-site', 'same-site'].includes(req.headers['sec-fetch-site'])) return null;
      if (req.headers.origin !== undefined) {
        // Never replace a foreign/null Origin with the trusted one.
        if (req.headers.origin !== publicOrigin) return null;
      } else {
        // Same-origin polling GETs can omit Origin. Bench's nginx supplies it;
        // this bridge requires a same-origin Referer before supplying that value.
        try {
          const referrer = new URL(req.headers.referer);
          if (referrer.origin !== publicOrigin || referrer.username || referrer.password) return null;
        } catch { return null; }
        headers.origin = publicOrigin;
      }
    }
    return { ...(socket ? socketTarget : webTarget), method: req.method, path: req.url, headers };
  };
  const isSocket = req => req.url.startsWith('/socket.io/') || req.url.startsWith('/socket.io?');
  const server = http.createServer((req, res) => {
    const target = options(req, isSocket(req));
    if (!target) {
      res.writeHead(403, { 'content-type': 'text/plain' });
      res.end('Staging socket origin refused');
      return;
    }
    const upstream = http.request(target, response => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    });
    upstream.on('error', () => {
      if (!res.headersSent) res.writeHead(502, { 'content-type': 'text/plain' });
      res.end('Staging upstream unavailable');
    });
    req.on('aborted', () => upstream.destroy());
    req.pipe(upstream);
  });
  server.on('upgrade', (req, client, head) => {
    if (!isSocket(req)) {
      client.end('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');
      return;
    }
    const target = options(req, true);
    if (!target) {
      client.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
      return;
    }
    const upstreamRequest = http.request(target);
    upstreamRequest.on('upgrade', (res, upstream, upstreamHead) => {
      const headers = [];
      for (let i = 0; i < res.rawHeaders.length; i += 2) {
        headers.push(`${res.rawHeaders[i]}: ${res.rawHeaders[i + 1]}`);
      }
      client.write(`HTTP/1.1 ${res.statusCode} ${res.statusMessage}\r\n${headers.join('\r\n')}\r\n\r\n`);
      if (head.length) upstream.write(head);
      if (upstreamHead.length) client.write(upstreamHead);
      upstream.on('error', () => client.destroy());
      client.on('error', () => upstream.destroy());
      client.on('close', () => upstream.destroy());
      upstream.on('close', () => client.destroy());
      upstream.pipe(client).pipe(upstream);
    });
    upstreamRequest.on('response', res => {
      res.resume();
      client.end(`HTTP/1.1 ${res.statusCode} ${res.statusMessage}\r\nConnection: close\r\n\r\n`);
    });
    upstreamRequest.on('error', () => client.destroy());
    client.on('error', () => upstreamRequest.destroy());
    upstreamRequest.end();
  });
  return server;
}

if (require.main === module) {
  const bench = '/home/frappe/frappe-bench-v4';
  const socketPath = process.env.ADM_ACCEPTANCE_SOCKET;
  if (fs.realpathSync(process.cwd()) !== bench || !socketPath ||
      !socketPath.startsWith(bench + '/logs/adm-realtime-') ||
      path.basename(socketPath) !== 'socket.io.sock' ||
      fs.realpathSync(path.dirname(socketPath)) !== path.dirname(socketPath)) {
    throw new Error('Only the guarded staging runtime is allowed');
  }
  const server = createProxy({ webTarget: { host: '127.0.0.1', port: 18004 },
    socketTarget: { socketPath }, site: 'test-administration-v4.local',
    publicOrigin: 'http://192.168.64.110:8004' });
  server.listen(8004, '0.0.0.0', () => console.log('Test UI with real-time: http://192.168.64.110:8004'));
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
}

module.exports = { createProxy };
