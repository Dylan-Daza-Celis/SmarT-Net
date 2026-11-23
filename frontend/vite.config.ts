import {defineConfig} from 'vite';

export default defineConfig({
 server:{proxy:{'/api':{target:process.env.SMARTIR_API_PROXY_TARGET??'http://127.0.0.1:8000',changeOrigin:false}},headers:{'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Permissions-Policy':'camera=(), microphone=(), geolocation=()'}},
 build:{rollupOptions:{output:{manualChunks(id){
  if(id.includes('node_modules')){
   if(/\/(recharts|recharts-scale|d3-[^/]+|victory-vendor)\//.test(id.replaceAll('\\','/')))return 'charts';
   if(/\/(redux|react-redux|@reduxjs|immer|reselect|use-sync-external-store)\//.test(id.replaceAll('\\','/')))return 'chart-state';
   return 'vendor';
  }
 }}}}
});
