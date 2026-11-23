// Same-origin proxy is the default: the browser never handles authentication tokens.
export const API = import.meta.env.VITE_API_URL ?? '';
export class ApiError extends Error {
 constructor(public status:number,message:string){super(message)}
}
let unauthorized=()=>{};
let epoch=0;
export function invalidateRequests(){epoch++}
export function onUnauthorized(callback:()=>void){unauthorized=callback;return ()=>{unauthorized=()=>{}}}
export async function apiResponse(path:string,init:RequestInit={}){
 const current=epoch;
 if(!path.startsWith('/api/'))throw Error('Ruta API inválida');
 const headers=new Headers(init.headers);
 if(init.body && typeof init.body==='string' && !headers.has('Content-Type'))headers.set('Content-Type','application/json');
 if(!['GET','HEAD','OPTIONS'].includes((init.method??'GET').toUpperCase()))headers.set('X-SmartIR-CSRF','1');
 const r=await fetch(API+path,{...init,headers,credentials:'include',cache:'no-store',redirect:'error'});
 if(r.status===401&&current===epoch)unauthorized();
 return r;
}
export async function checkResponse(r:Response){
 if(r.ok)return r;
 const body=await r.json().catch(()=>null);
 const detail=typeof body?.detail==='string'?body.detail:r.status===422?'Revise los campos y el intervalo de fechas.':'No se pudo completar la solicitud.';
 throw new ApiError(r.status,`${detail} (HTTP ${r.status})${r.status===429?` Retry-After: ${r.headers.get('Retry-After')??'?'} s`:''}`);
}
export async function request(path:string,init:RequestInit={}){
 const r=await checkResponse(await apiResponse(path,init));return r.status===204?null:r.json();
}
export async function download(path:string){
 const r=await checkResponse(await apiResponse(path));
 const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');
 a.href=url;a.download=r.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'smartir-report.json';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
