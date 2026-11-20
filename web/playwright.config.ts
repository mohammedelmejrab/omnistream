import { defineConfig, devices } from '@playwright/test';

// Real-browser checks against the real FastAPI app (fake model runtime, seeded DB).
// The server serves web/dist under /app, so run `npm run build` first (test:e2e does).
const PORT = 8765;
const PYTHON = process.env['OMNISTREAM_PYTHON'] ?? '../.venv/bin/python';

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts/,
  outputDir: './e2e/.results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `${PYTHON} e2e/support/serve_e2e.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/chats`,
    reuseExistingServer: false,
    timeout: 120_000,
    // Slow retrieval keeps a run live for a couple of seconds so the trace can be watched.
    env: { OMNISTREAM_E2E_RETRIEVE_DELAY_MS: '2000' },
  },
});
