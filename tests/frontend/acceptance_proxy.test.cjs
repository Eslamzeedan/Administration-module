const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const { once } = require('node:events');
const { createProxy } = require('../../tools/v4_acceptance_proxy.cjs');

async function listen(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return { host: '127.0.0.1', port: server.address().port };
}

async function fixtures(t) {
  const upgraded = new Set();
  const web = http.createServer((req, res) => {
    let body = '';
    req.on('data', data => body += data);
    req.on('end', () => res.end(JSON.stringify({ via: 'web', path: req.url,
      site: req.headers['x-frappe-site-name'], host: req.headers.host, body })));
  });
  const socket = http.createServer((req, res) => res.end(JSON.stringify({ via: 'socket',
    site: req.headers['x-frappe-site-name'], origin: req.headers.origin, cookie: req.headers.cookie })));
  socket.on('upgrade', (req, client, head) => {
    upgraded.add(client);
    client.on('close', () => upgraded.delete(client));
    client.on('end', () => client.end());
    client.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n');
    if (head.length) client.write(head);
    client.on('data', data => client.write(data));
    client.on('error', () => {});
  });
  const webTarget = await listen(web), socketTarget = await listen(socket);
  const proxy = createProxy({ webTarget, socketTarget, site: 'test-administration-v4.local' });
  const target = await listen(proxy);
  t.after(() => { for (const client of upgraded) client.destroy();
    proxy.closeAllConnections(); web.closeAllConnections(); socket.closeAllConnections();
    proxy.close(); web.close(); socket.close(); });
  return target;
}

function request(target, path, method = 'GET', headers = {}, body = '') {
  return new Promise((resolve, reject) => {
    const req = http.request({ ...target, path, method, headers }, res => {
      let text = '';
      res.on('data', chunk => text += chunk);
      res.on('end', () => resolve({ status: res.statusCode, text }));
    });
    req.on('error', reject); req.end(body);
  });
}

test('staging proxy preserves normal requests and fixes the site header', async t => {
  const target = await fixtures(t);
  const r = await request(target, '/api/method/example?x=1', 'POST',
    { 'x-frappe-site-name': 'production', host: 'test-ui:8004' }, 'synthetic=payload');
  assert.equal(r.status, 200);
  assert.deepEqual(JSON.parse(r.text), { via: 'web', path: '/api/method/example?x=1',
    site: 'test-administration-v4.local', host: 'test-ui:8004', body: 'synthetic=payload' });
});

test('socket polling keeps same-origin authentication and cannot select another site', async t => {
  const target = await fixtures(t);
  const r = await request(target, '/socket.io/?EIO=4&transport=polling', 'GET',
    { origin: 'http://test-ui:8004', cookie: 'sid=synthetic-test-only', 'x-frappe-site-name': 'production' });
  assert.deepEqual(JSON.parse(r.text), { via: 'socket', site: 'test-administration-v4.local',
    origin: 'http://test-ui:8004', cookie: 'sid=synthetic-test-only' });
});

test('websocket upgrade and bytes cross the fixed socket upstream', async t => {
  const target = await fixtures(t);
  const client = net.connect(target.port, target.host);
  await once(client, 'connect');
  t.after(() => client.destroy());
  client.write('GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\nHost: test-ui:8004\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n');
  const [headers] = await once(client, 'data');
  assert.match(headers.toString(), /^HTTP\/1.1 101 /);
  client.write('synthetic-websocket-bytes');
  const [echo] = await once(client, 'data');
  assert.equal(echo.toString(), 'synthetic-websocket-bytes');
  client.destroy();
});

test('unrelated upgrades are refused', async t => {
  const target = await fixtures(t);
  const r = await request(target, '/unrelated', 'GET', { connection: 'Upgrade', upgrade: 'websocket' });
  assert.equal(r.status, 404);
});
