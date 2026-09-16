import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 10 },
    { duration: '20s', target: 50 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250'],
  },
};

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:10000';
export default function () {
  const res = http.get(`${BASE}/healthz`);
  check(res, { 'health 200': (r) => r.status === 200 });
  sleep(0.05);
}
