import {createContext,useCallback,useContext,useEffect,useRef,useState,ReactNode} from 'react';
import {ApiError,invalidateRequests,onUnauthorized,request} from '../api';
import type {User} from '../types';
type Session={user:User;expires_at:number;expires_in:number};
type State='restoring'|'ready'|'anonymous'|'unavailable';
type Context={user:User|null;state:State;message:string;login:(username:string,password:string)=>Promise<void>;logout:()=>Promise<void>;restore:()=>Promise<void>};
const Auth=createContext<Context|null>(null);
export function SessionProvider({children}:{children:ReactNode}){
 const [user,setUser]=useState<User|null>(null),[state,setState]=useState<State>('restoring'),[message,setMessage]=useState('');
 const generation=useRef(0),timer=useRef<ReturnType<typeof setTimeout>>();
 const invalidate=useCallback(()=>{generation.current++;invalidateRequests();clearTimeout(timer.current);setUser(null);setState('anonymous');setMessage('La sesión ha finalizado. Inicie sesión para continuar.');},[]);
 const restoreRef=useRef<()=>Promise<void>>(async()=>{});
 const accept=useCallback((s:Session)=>{
  if(s.user.eve_only)throw new Error('Cuenta exclusiva del agente EVE; no dispone de acceso interactivo.');
  setUser(s.user);setState('ready');setMessage('');clearTimeout(timer.current);
  timer.current=setTimeout(()=>void restoreRef.current(),Math.max(1,s.expires_in)*1000+100);
 },[]);
 const restore=useCallback(async()=>{
  const current=generation.current;
  try{const s=await request('/api/auth/session');if(current===generation.current)accept(s)}
  catch(e){if(current!==generation.current)return;if(e instanceof ApiError&&[401,403].includes(e.status)){invalidate()}else{setState('unavailable');setMessage('No se pudo verificar la sesión con la API. Reintente; no se borró la cookie.')}}
 },[accept,invalidate]);
 restoreRef.current=restore;
 useEffect(()=>{const off=onUnauthorized(invalidate);void restore();
  const focus=()=>{if(document.visibilityState==='visible')void restore()};
  window.addEventListener('focus',focus);document.addEventListener('visibilitychange',focus);
  return()=>{off();clearTimeout(timer.current);window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',focus)};
 },[invalidate,restore]);
 const login=useCallback(async(username:string,password:string)=>{
  generation.current++;invalidateRequests();const s=await request('/api/auth/session',{method:'POST',body:JSON.stringify({username,password})});accept(s);
 },[accept]);
 const logout=useCallback(async()=>{
  await request('/api/auth/session',{method:'DELETE'});generation.current++;invalidateRequests();clearTimeout(timer.current);
  setUser(null);setState('anonymous');setMessage('Sesión cerrada.');
 },[]);
 return <Auth.Provider value={{user,state,message,login,logout,restore}}>{children}</Auth.Provider>;
}
export function useSession(){const s=useContext(Auth);if(!s)throw Error('SessionProvider required');return s}
