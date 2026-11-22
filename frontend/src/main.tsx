import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
const API = 'http://localhost:8000';
type User = {id:string; username:string; role:'administrador'|'analista'|'observador'};
type Incident = {id:string; event_type:string; destination_ip:string|null; status:string; score:number; priority:string; event_count:number; explanation:Record<string,number>; events?:{id:string; source:string; message:string}[]};
type History = {id:string; author:string; previous_status:string|null; status:string; justification:string; created_at:string};
type Action = {id:string; author:string; description:string; created_at:string};
const statuses = ['Nuevo','Asignado','En análisis','En respuesta','Resuelto','Cerrado'];
function App(){
 const [stats,setStats]=useState({events:0,incidents:0,critical:0,high:0});
 const [token,setToken]=useState(''), [user,setUser]=useState<User|null>(null);
 const [username,setUsername]=useState(''), [password,setPassword]=useState('');
 const [items,setItems]=useState<Incident[]>([]), [detail,setDetail]=useState<Incident|null>(null);
 const [history,setHistory]=useState<History[]>([]), [actions,setActions]=useState<Action[]>([]);
 const [status,setStatus]=useState('Nuevo'), [reason,setReason]=useState(''), [action,setAction]=useState('');
 const [error,setError]=useState(''), [busy,setBusy]=useState(false);
 const canEdit=user?.role==='administrador'||user?.role==='analista';
 function logout(){setToken('');setUser(null);setItems([]);setDetail(null);setHistory([]);setActions([]);setPassword('')}
 async function request(path:string, init:RequestInit={}, access=token){
  const r=await fetch(API+path,{...init,headers:{'Content-Type':'application/json',...(access?{Authorization:`Bearer ${access}`}:{})}});
  if(!r.ok){if(r.status===401 && access)logout();const body=await r.json().catch(()=>({detail:'API no disponible'}));throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))}
  return r.json();
 }
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const data=await request('/api/auth/login',{method:'POST',body:JSON.stringify({username,password})},'');const me=await request('/api/auth/me',{},data.access_token);setUser(me);setToken(data.access_token);setPassword('')}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function load(){try{const [incidents,summary]=await Promise.all([request('/api/incidents'),request('/api/stats')]);setItems(incidents);setStats(summary);setError('')}catch(e){setError(String(e))}}
 useEffect(()=>{if(token)void load()},[token]);
 async function openDetail(id:string){setDetail(null);setError('');setReason('');setAction('');try{const [i,h,a]=await Promise.all([request(`/api/incidents/${id}`),request(`/api/incidents/${id}/history`),request(`/api/incidents/${id}/actions`)]);setDetail(i);setStatus(i.status);setHistory(h);setActions(a)}catch(e){setError(String(e))}}
 async function saveStatus(e:React.FormEvent){e.preventDefault();if(!detail)return;setBusy(true);setError('');try{await request(`/api/incidents/${detail.id}/status`,{method:'PATCH',body:JSON.stringify({status,justification:reason})});await openDetail(detail.id);await load()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function saveAction(e:React.FormEvent){e.preventDefault();if(!detail)return;setBusy(true);setError('');try{await request(`/api/incidents/${detail.id}/actions`,{method:'POST',body:JSON.stringify({description:action})});await openDetail(detail.id)}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function importFile(file:File){setBusy(true);setError('');try{const text=await file.text();const parsed=file.name.endsWith('.jsonl')?text.split(/\r?\n/).filter(Boolean).map(x=>JSON.parse(x)):JSON.parse(text);const result=await request('/api/events/import',{method:'POST',body:JSON.stringify(Array.isArray(parsed)?{events:parsed}:parsed)});alert(`Importados: ${result.imported}. Duplicados: ${result.duplicates}`);await load();if(detail)await openDetail(detail.id)}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <main><header><div><h1>SmartIR-Net</h1><p>Gestión de incidentes de seguridad</p></div>{user&&<div><p>{user.username} · {user.role}</p><button onClick={logout}>Cerrar sesión</button></div>}</header>{error&&<p role="alert" className="error">{error}</p>}
 {!user?<section className="panel"><h2>Iniciar sesión</h2><form onSubmit={login}><label>Usuario<input autoComplete="username" required maxLength={100} value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Contraseña<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy}>Entrar</button></form></section>:<>
 <section className="metrics">{[["Eventos",stats.events],["Incidentes",stats.incidents],["Prioridad alta",stats.high],["Prioridad crítica",stats.critical]].map(([label,value])=><article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section><section className="panel"><div className="tools"><h2>Incidentes</h2><button onClick={load}>Actualizar</button>{canEdit&&<label className="upload">Importar JSON / JSONL<input disabled={busy} type="file" accept=".json,.jsonl" onChange={e=>{const f=e.target.files?.[0];if(f)void importFile(f);e.currentTarget.value=''}}/></label>}</div><div className="scroll"><table><thead><tr><th>Tipo</th><th>Destino</th><th>Eventos</th><th>Riesgo</th><th>Prioridad</th><th>Estado</th><th/></tr></thead><tbody>{items.map(i=><tr key={i.id}><td>{i.event_type.replace(/_/g,' ')}</td><td>{i.destination_ip||'No indicado'}</td><td>{i.event_count}</td><td>{i.score}/100</td><td>{i.priority}</td><td>{i.status}</td><td><button onClick={()=>openDetail(i.id)}>Detalle</button></td></tr>)}</tbody></table>{items.length===0&&<p>Sin incidentes registrados.</p>}</div></section>
 {detail&&<section className="panel"><div className="tools"><h2>{detail.event_type} · {detail.status}</h2><button onClick={()=>setDetail(null)}>Cerrar detalle</button></div><pre>{JSON.stringify(detail.explanation,null,2)}</pre>
 {canEdit&&<form onSubmit={saveStatus}><label>Estado<select value={status} onChange={e=>setStatus(e.target.value)}>{statuses.map(s=><option key={s}>{s}</option>)}</select></label><label>Justificación<textarea required maxLength={4000} value={reason} onChange={e=>setReason(e.target.value)}/></label><button disabled={busy||status===detail.status||!reason.trim()}>Guardar estado</button></form>}
 <h3>Historial de estados</h3>{history.length===0&&<p>Sin historial registrado; puede ser un incidente anterior a la migración.</p>}{history.map(h=><article key={h.id}><p>{h.previous_status||'Creación'} → {h.status} · {h.author} · {new Date(h.created_at).toLocaleString()}</p><p>{h.justification}</p></article>)}
 <h3>Acciones de respuesta</h3>{actions.map(a=><article key={a.id}><p>{a.author} · {new Date(a.created_at).toLocaleString()}</p><p>{a.description}</p></article>)}{canEdit&&<form onSubmit={saveAction}><label>Acción realizada<textarea required maxLength={4000} value={action} onChange={e=>setAction(e.target.value)}/></label><button disabled={busy||!action.trim()}>Registrar acci?n</button></form>}
 <h3>Eventos</h3>{detail.events?.map(e=><p key={e.id}>{e.source}: {e.message}</p>)}</section>}</>}
 <footer>Laboratorio académico · Las sesiones duran 15 minutos.</footer></main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
