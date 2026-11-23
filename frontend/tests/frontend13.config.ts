import {defineConfig} from '@playwright/test';
const port=Number(process.env.VALIDATION_WEB_PORT);
if(!port||!process.env.VALIDATION_CREDENTIALS)throw Error('Run via validation.run_frontend13');
export default defineConfig({testDir:'.',testMatch:'frontend13.spec.ts',workers:1,retries:0,timeout:90000,
 reporter:'dot',outputDir:`../../.test-runs/iter13-playwright-${port}`,
 use:{baseURL:`http://127.0.0.1:${port}`,browserName:'chromium',headless:true,actionTimeout:12000,
 viewport:{width:1440,height:1050},trace:'off',video:'off',screenshot:'off'},
 webServer:{cwd:process.cwd(),command:'node node_modules/vite/bin/vite.js --config tests/vite.validation.ts',
 url:`http://127.0.0.1:${port}`,reuseExistingServer:false,timeout:30000}});
