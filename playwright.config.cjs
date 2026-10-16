const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'./tests',testMatch:'*.spec.cjs',fullyParallel:true,
  retries:process.env.CI?1:0,reporter:'list',
  use:{baseURL:'http://127.0.0.1:4173',browserName:'chromium',
    channel:process.env.PLAYWRIGHT_BROWSER_CHANNEL||undefined,
    viewport:{width:1440,height:1000},colorScheme:'light',screenshot:'only-on-failure'},
  webServer:{command:'python -m http.server 4173 --bind 127.0.0.1 --directory _site',
    url:'http://127.0.0.1:4173',reuseExistingServer:!process.env.CI,timeout:15000}
});
