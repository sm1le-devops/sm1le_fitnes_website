import http from 'k6/http';
import { check, fail } from 'k6';

const BASE_URL =
  __ENV.BASE_URL ||
  'http://127.0.0.1:8000';

const USERNAME = __ENV.LOAD_TEST_USERNAME;
const PASSWORD = __ENV.LOAD_TEST_PASSWORD;

const VUS = Number(__ENV.VUS || 25);
const DURATION = __ENV.DURATION || '60s';

export const options = {
  scenarios: {
    authenticated_profile: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
      gracefulStop: '10s',
    },
  },

  thresholds: {
    'http_req_duration{endpoint:profile}': [
      'p(95)<500',
    ],

    'http_req_failed{endpoint:profile}': [
      'rate<0.01',
    ],
  },
};

export function setup() {
  if (!USERNAME || !PASSWORD) {
    fail(
      'LOAD_TEST_USERNAME and LOAD_TEST_PASSWORD must be set'
    );
  }

  // 1. Get a valid CSRF token.
  const loginPage = http.get(
    `${BASE_URL}/auth/login`,
    {
      redirects: 0,
      tags: {
        endpoint: 'setup_login_page',
      },
    }
  );

  if (loginPage.status !== 200) {
    fail(
      `Login page failed: HTTP ${loginPage.status}`
    );
  }

  const csrfCookie =
    loginPage.cookies.csrf_token;

  if (
    !csrfCookie ||
    csrfCookie.length === 0
  ) {
    fail(
      'CSRF cookie was not returned by /auth/login'
    );
  }

  const csrfToken =
    csrfCookie[0].value;

  // 2. Authenticate once.
  const loginResponse = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({
      username: USERNAME,
      password: PASSWORD,
      csrf_token: csrfToken,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        Cookie:
          `csrf_token=${csrfToken}`,
      },

      redirects: 0,

      tags: {
        endpoint: 'setup_login',
      },
    }
  );

  const loginOk = check(
    loginResponse,
    {
      'setup login returned 200': (r) =>
        r.status === 200,
    }
  );

  if (!loginOk) {
    fail(
      `Login failed: HTTP ${loginResponse.status} ${loginResponse.body}`
    );
  }

  const sessionCookie =
    loginResponse.cookies.session_id;

  if (
    !sessionCookie ||
    sessionCookie.length === 0
  ) {
    fail(
      'session_id cookie was not returned after login'
    );
  }

  return {
    sessionId:
      sessionCookie[0].value,
  };
}

export default function (data) {
  const response = http.get(
    `${BASE_URL}/auth/profile`,
    {
      headers: {
        Cookie:
          `session_id=${data.sessionId}`,
      },

      // Important:
      // if auth breaks, /profile returns a redirect.
      // We do not want k6 to follow it and falsely count
      // the final login page as HTTP 200.
      redirects: 0,

      timeout: '5s',

      tags: {
        endpoint: 'profile',
        test: 'authenticated_capacity',
      },
    }
  );

  check(response, {
    'profile returned 200': (r) =>
      r.status === 200,

    'authenticated user rendered': (r) =>
        r.status === 200 &&
        typeof r.body === 'string' &&
        r.body.includes(USERNAME)
  });
}