import http from 'http';

const SECRET = 'scaleezy_internal_secret_key_2026';

function makeRequest(options, data) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => resolve({ statusCode: res.statusCode, body: body ? JSON.parse(body) : {} }));
    });
    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

async function test() {
  console.log('--- Test 1: Unauthorized Request (Missing Secret Header) ---');
  const res1 = await makeRequest({
    hostname: '127.0.0.1',
    port: 3001,
    path: '/whatsapp/send-message',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  }, { phone: '919876543210', message: 'Hello test' });
  console.log('Result 1:', res1);

  console.log('\n--- Test 2: Authorized Request (With Secret Header) ---');
  const res2 = await makeRequest({
    hostname: '127.0.0.1',
    port: 3001,
    path: '/whatsapp/send-message',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Internal-API-Secret': SECRET
    }
  }, { phone: '919876543210', message: 'Hello test' });
  console.log('Result 2:', res2);
}

test().catch(console.error);
