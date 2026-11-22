import {defineConfig} from '@playwright/test';
const port=Number(process.env.VALIDATION_WEB_PORT);
if(!port||!process.env.VALIDATION_CREDENTIALS)throw Error('Run via python -m validation.run_integral --browser');
export default defineConfig({testDir:'.',testMatch:'integral.spec.ts',workers:1,retries:0,timeout:180000,
 reporter:'dot',outputDir:'../../.test-runs/iter10-playwright',
 use:{baseURL:`http://127.0.0.1:${port}`,browserName:'chromium',headless:true,actionTimeout:15000,viewport:{width:1440,height:1100},
      trace:'off',video:'off',screenshot:'off'},
 webServer:{cwd:process.cwd(),command:'node node_modules/vite/bin/vite.js --config tests/vite.validation.ts',url:`http://127.0.0.1:${port}`,reuseExistingServer:false,timeout:30000}});
