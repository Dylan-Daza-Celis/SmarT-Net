import {defineConfig} from 'vite';

export default defineConfig({
 build:{rollupOptions:{output:{manualChunks(id){
  if(id.includes('node_modules')){
   if(/\/(recharts|recharts-scale|d3-[^/]+|victory-vendor)\//.test(id.replaceAll('\\','/')))return 'charts';
   if(/\/(redux|react-redux|@reduxjs|immer|reselect|use-sync-external-store)\//.test(id.replaceAll('\\','/')))return 'chart-state';
   return 'vendor';
  }
 }}}}
});
