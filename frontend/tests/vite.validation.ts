import {defineConfig, mergeConfig} from 'vite';
import base from '../vite.config';
const target=process.env.VALIDATION_API_TARGET??'';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(target))throw Error('Only the isolated loopback API is allowed');
export default mergeConfig(base,defineConfig({server:{host:'127.0.0.1',port:Number(process.env.VALIDATION_WEB_PORT),strictPort:true,proxy:{'/api':target,'/health':target}}}));
