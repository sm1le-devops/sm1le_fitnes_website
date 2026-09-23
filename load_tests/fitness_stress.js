import http from 'k6/http';
import { check } from 'k6';

const VUS = Number(__ENV.VUS || 250);

export const options = {
  stages: [
    { duration: '15s', target: VUS },
    { duration: '45s', target: VUS },
    { duration: '15s', target: 0 },
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
    `${BASE_URL}/ready`,
    {
      timeout: '5s',
      tags: {
        test_type: 'readiness_capacity',
      },
    }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'service is ready': (r) =>
      r.body.includes('"status":"ready"'),
  });
}