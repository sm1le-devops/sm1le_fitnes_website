import http from 'k6/http';
import { check } from 'k6';

const VUS = Number(__ENV.VUS || 100);
const DURATION = __ENV.DURATION || '60s';

export const options = {
  scenarios: {
    capacity: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
      gracefulStop: '10s',
    },
  },

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
        endpoint: 'ready',
        test: 'capacity',
      },
    }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,

    'database and redis are ready': (r) =>
      r.body.includes('"status":"ready"'),
  });
}