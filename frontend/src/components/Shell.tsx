import {ReactNode,useEffect,useRef,useState} from 'react';
import {useSession} from '../auth/SessionProvider';
import {Route} from '../navigation';
import {Notice} from './ui';
const navigation=[['dashboard','Resumen','M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z'],['incidents','Incidentes','M12 3 2 21h20L12 3zm0 6v5m0 3v1'],['analytics','Analítica y reportes','M4 20V10m8 10V4m8 16v-7'],['import','Importación','M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4'],['evaluation','Evaluación','M5 4h14v17H5zM8 8h8m-8 4h8m-8 4h5'],['ml','Machine learning','M9 3H5v6m10-6h4v6M5 15v6h4m6 0h4v-6M9 9h6v6H9z']];
export default function Shell({route,children}:{route:Route;children:ReactNode}){
 const {user,logout}=useSession();const [open,setOpen]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const menuButton=useRef<HTMLButtonElement>(null),menu=useRef<HTMLElement>(null);
 const locations=useRef<Record<string,string>>({});locations.current[route.path]=`#/${route.path}${route.search.size?'?'+route.search:''}`;
 useEffect(()=>{setOpen(false)},[route.path]);
 useEffect(()=>{if(!open)return;menu.current?.querySelector('a')?.focus();const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setOpen(false);menuButton.current?.focus()}};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape)},[open]);
 async function end(){setBusy(true);try{await logout()}catch(e){setError('No se pudo cerrar la sesión en la API. Reintente.')}finally{setBusy(false)}}
 return <div className="app-layout"><a className="skip-link" href="#workspace" onClick={e=>{e.preventDefault();document.getElementById('workspace')?.focus()}}>Saltar al contenido</a>
 <aside className={`sidebar ${open?'is-open':''}`}><a href="#/dashboard" className="brand" aria-label="SmartIR-Net inicio"><span className="brand-mark" aria-hidden="true">S</span><span>SmartIR<span className="brand-net">-Net</span><small>SECURITY OPERATIONS</small></span></a>
 <div className="nav-label">ESPACIO DE TRABAJO</div><nav ref={menu} aria-label="Navegación principal">{navigation.filter(([id])=>id!=='import'||user?.role!=='observador').map(([id,label,path])=><a href={locations.current[id]??`#/${id}`} onClick={()=>{setOpen(false);document.getElementById("workspace")?.focus()}} key={id} aria-current={route.path===id?'page':undefined}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={path}/></svg>{label}</a>)}</nav>
 <div className="sidebar-note"><p>Datos operativos y experimentales identificados por su procedencia.</p></div></aside>
 {open&&<button className="nav-backdrop" aria-label="Cerrar navegación" onClick={()=>setOpen(false)}/>}
 <div className="workspace"><header className="topbar"><div className="topbar-left"><button ref={menuButton} className="nav-toggle button-quiet" aria-label={open?'Cerrar menú':'Abrir menú'} aria-expanded={open} onClick={()=>setOpen(!open)}>☰</button><span className="breadcrumb">Plataforma / <strong>{navigation.find(([id])=>id===route.path)?.[1]??'Página'}</strong></span></div><div className="session-tools"><span className="utc-label">UTC</span><div className="user-avatar" aria-hidden="true">{user?.username[0].toUpperCase()}</div><div className="identity"><strong>{user?.username}</strong><span>{user?.role}</span></div><button className="button-secondary" onClick={()=>void end()} disabled={busy}>Cerrar sesión</button></div></header>
 <main id="workspace" tabIndex={-1} className="page-content">{error&&<Notice tone="error">{error}</Notice>}{children}<footer>SmartIR-Net · Laboratorio académico · Las métricas describen evidencia registrada, no eficacia certificada.</footer></main></div></div>;
}
