import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '20s', target: 50 },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 250 },
    { duration: '20s', target: 0 },
  ],

  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

const BASE_URL =
  __ENV.BASE_URL ||
  'http://127.0.0.1:8000';

export default function () {
  const response = http.get(
    `${BASE_URL}/ready`
  );

  check(response, {
    'status is 200': (r) =>
      r.status === 200,

    'response is ready': (r) =>
      r.body.includes('"status":"ready"'),
  });

  sleep(1);
}