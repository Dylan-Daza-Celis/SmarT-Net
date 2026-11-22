import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import Evaluation from './Evaluation';
const API = 'http://localhost:8000';
type User = {id:string; username:string; role:'administrador'|'analista'|'observador'};
type ImportReport = {imported:number;duplicates:number;discarded?:number;unknown?:number;batches?:number;complete?:boolean;errors?:{line:number|null;code:string;fields:string[]}[];errors_omitted?:number};
type EventView = {id:string;source:string;message:string;asset_criticality:number;asset_criticality_observed:boolean|null;adapter_metadata:Record<string,unknown>|null};
type Incident = {id:string; event_type:string; destination_ip:string|null; status:string; score:number; priority:string; event_count:number; explanation:{algorithm_version?:string; factors?:Record<string,{value:number;weight:number;contribution:number;observed:boolean;basis?:string}>; context?:{known:boolean;policy:string}}; events?:EventView[]};
type History = {id:string; author:string; previous_status:string|null; status:string; justification:string; created_at:string};
type Action = {id:string; author:string; description:string; created_at:string};
const statuses = ['Nuevo','Asignado','En análisis','En respuesta','Resuelto','Cerrado'];
function App(){
 const [priorityFilter,setPriorityFilter]=useState(''),[typeFilter,setTypeFilter]=useState(''),[stateFilter,setStateFilter]=useState('');
 const [format,setFormat]=useState('smartir'),[sensor,setSensor]=useState('suricata'),[report,setReport]=useState<ImportReport|null>(null),[evidence,setEvidence]=useState<unknown>(null);
 const [stats,setStats]=useState({events:0,incidents:0,critical:0,high:0});
 const [token,setToken]=useState(''), [user,setUser]=useState<User|null>(null);
 const [username,setUsername]=useState(''), [password,setPassword]=useState('');
 const [items,setItems]=useState<Incident[]>([]), [detail,setDetail]=useState<Incident|null>(null);
 const [history,setHistory]=useState<History[]>([]), [actions,setActions]=useState<Action[]>([]);
 const [status,setStatus]=useState('Nuevo'), [reason,setReason]=useState(''), [action,setAction]=useState('');
 const [error,setError]=useState(''), [busy,setBusy]=useState(false);
 const filtered=items.filter(i=>(!priorityFilter||i.priority===priorityFilter)&&(!typeFilter||i.event_type===typeFilter)&&(!stateFilter||i.status===stateFilter));
 const canEdit=user?.role==='administrador'||user?.role==='analista';
 function logout(){setToken('');setUser(null);setItems([]);setDetail(null);setHistory([]);setActions([]);setPassword('');setReport(null);setEvidence(null)}
 async function request(path:string, init:RequestInit={}, access=token){
  const r=await fetch(API+path,{...init,headers:{'Content-Type':'application/json',...(access?{Authorization:`Bearer ${access}`}:{})}});
  if(!r.ok){if(r.status===401 && access)logout();const body=await r.json().catch(()=>({detail:'API no disponible'}));throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))}
  return r.json();
 }
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const data=await request('/api/auth/login',{method:'POST',body:JSON.stringify({username,password})},'');const me=await request('/api/auth/me',{},data.access_token);setUser(me);setToken(data.access_token);setPassword('')}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function load(){try{const [incidents,summary]=await Promise.all([request('/api/incidents'),request('/api/stats')]);setItems(incidents);setStats(summary);setError('')}catch(e){setError(String(e))}}
 useEffect(()=>{if(token)void load()},[token]);
 async function openDetail(id:string){setDetail(null);setEvidence(null);setError('');setReason('');setAction('');try{const [i,h,a]=await Promise.all([request(`/api/incidents/${id}`),request(`/api/incidents/${id}/history`),request(`/api/incidents/${id}/actions`)]);setDetail(i);setStatus(i.status);setHistory(h);setActions(a)}catch(e){setError(String(e))}}
 async function saveStatus(e:React.FormEvent){e.preventDefault();if(!detail)return;setBusy(true);setError('');try{await request(`/api/incidents/${detail.id}/status`,{method:'PATCH',body:JSON.stringify({status,justification:reason})});await openDetail(detail.id);await load()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function saveAction(e:React.FormEvent){e.preventDefault();if(!detail)return;setBusy(true);setError('');try{await request(`/api/incidents/${detail.id}/actions`,{method:'POST',body:JSON.stringify({description:action})});await openDetail(detail.id)}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function importFile(file:File){
  setBusy(true);setError('');setReport(null);
  try{
   if(file.size>10*1024*1024)throw new Error('El archivo supera 10 MiB');
   let result:ImportReport;
   if(format==='eve'){
    const response=await fetch(`${API}/api/events/import/eve?filename=${encodeURIComponent(file.name)}&sensor_id=${encodeURIComponent(sensor)}`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/x-ndjson'},body:file});
    if(response.status===401)logout();
    const body=await response.json();
    if(!response.ok&&response.status!==413)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));
    result=body;
    if(!response.ok)setError('Se alcanzaron los límites; el reporte indica los lotes conservados.');
   }else{
    const text=await file.text();
    const parsed=file.name.endsWith('.jsonl')?text.split(/\r?\n/).filter(Boolean).map(x=>JSON.parse(x)):JSON.parse(text);
    result=await request('/api/events/import',{method:'POST',body:JSON.stringify(Array.isArray(parsed)?{events:parsed}:parsed)});
   }
   setReport(result);await load();if(detail)await openDetail(detail.id);
   if(result.complete===false)setError('Importación parcial por límite; revise el reporte.');
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function showEvidence(id:string){try{const [event,provenance]=await Promise.all([request(`/api/events/${id}`),request(`/api/events/${id}/evidence?limit=10`)]);setEvidence({event,provenance})}catch(e){setError(String(e))}}
 return <main><header><div><h1>SmartIR-Net</h1><p>Gestión de incidentes de seguridad</p></div>{user&&<div><p>{user.username} · {user.role}</p><button onClick={logout}>Cerrar sesión</button></div>}</header>{error&&<p role="alert" className="error">{error}</p>}
 {!user?<section className="panel"><h2>Iniciar sesión</h2><form onSubmit={login}><label>Usuario<input autoComplete="username" required maxLength={100} value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Contraseña<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy}>Entrar</button></form></section>:<>
 <Evaluation token={token} researcher={user.role==='administrador'} request={request}/><section className="metrics">{[["Eventos",stats.events],["Incidentes",stats.incidents],["Prioridad alta",stats.high],["Prioridad crítica",stats.critical]].map(([label,value])=><article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section><section className="panel"><div className="tools"><h2>Incidentes</h2><button onClick={load}>Actualizar</button>{canEdit&&<><label>Formato<select disabled={busy} value={format} onChange={e=>setFormat(e.target.value)}><option value="smartir">SmartIR JSON / JSONL</option><option value="eve">Suricata EVE JSON Lines</option></select></label>{format==='eve'&&<label>Sensor declarado<input value={sensor} maxLength={80} pattern="[a-zA-Z0-9_.:-]+" required onChange={e=>setSensor(e.target.value)}/></label>}<label className="upload">{busy?'Importando...':'Importar archivo'}<input disabled={busy} type="file" accept=".json,.jsonl,.ndjson" onChange={e=>{const f=e.target.files?.[0];if(f)void importFile(f);e.currentTarget.value=''}}/></label></>}</div>{report&&<section aria-live="polite"><h3>Resultado de importación</h3><p>Importados: {report.imported} | Duplicados: {report.duplicates} | Descartados: {report.discarded??0} | Desconocidos: {report.unknown??0} | Lotes: {report.batches??1}</p>{report.errors?.map((e,index)=><p key={index} className="error">Línea {e.line??'-'}: {e.code} {e.fields.join(', ')}</p>)}{!!report.errors_omitted&&<p>Errores adicionales omitidos del reporte: {report.errors_omitted}</p>}</section>}<div className="tools"><label>Prioridad<select value={priorityFilter} onChange={e=>setPriorityFilter(e.target.value)}><option value="">Todas</option>{['Baja','Media','Alta','Crítica'].map(p=><option key={p}>{p}</option>)}</select></label><label>Tipo<select value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}><option value="">Todos</option>{[...new Set(items.map(i=>i.event_type))].map(t=><option key={t}>{t}</option>)}</select></label><label>Estado<select value={stateFilter} onChange={e=>setStateFilter(e.target.value)}><option value="">Todos</option>{statuses.map(s=><option key={s}>{s}</option>)}</select></label></div><div className="scroll"><table><thead><tr><th>Tipo</th><th>Destino</th><th>Eventos</th><th>Riesgo</th><th>Prioridad</th><th>Estado</th><th/></tr></thead><tbody>{filtered.map(i=><tr key={i.id}><td>{i.event_type.replace(/_/g,' ')}</td><td>{i.destination_ip||'No indicado'}</td><td>{i.event_count}</td><td>{i.score}/100</td><td>{i.priority}</td><td>{i.status}</td><td><button onClick={()=>openDetail(i.id)}>Detalle</button></td></tr>)}</tbody></table>{filtered.length===0&&<p>Sin incidentes registrados.</p>}</div></section>
 {detail&&<section className="panel"><div className="tools"><h2>{detail.event_type} · {detail.status}</h2><button onClick={()=>setDetail(null)}>Cerrar detalle</button></div><p>Riesgo: {detail.score}/100 | {detail.priority}</p>{detail.explanation.factors?<><p>Algoritmo: {detail.explanation.algorithm_version}</p><table><thead><tr><th>Factor</th><th>Valor</th><th>Peso</th><th>Aporte</th></tr></thead><tbody>{Object.entries(detail.explanation.factors).map(([name,f])=><tr key={name}><td>{name}{f.basis?` (${f.basis})`:!f.observed?' (valor de política, no observado)':''}</td><td>{f.value}</td><td>{f.weight*100}%</td><td>{f.contribution}</td></tr>)}</tbody></table><p>Contexto desconocido: valor de política {detail.explanation.factors.context?.value}; no es un dato observado.</p></>:<p>Evaluación heredada: versión y parámetros originales no registrados.</p>}<details><summary>Explicación completa</summary><pre>{JSON.stringify(detail.explanation,null,2)}</pre></details>
 {canEdit&&<form onSubmit={saveStatus}><label>Estado<select value={status} onChange={e=>setStatus(e.target.value)}>{statuses.map(s=><option key={s}>{s}</option>)}</select></label><label>Justificación<textarea required maxLength={4000} value={reason} onChange={e=>setReason(e.target.value)}/></label><button disabled={busy||status===detail.status||!reason.trim()}>Guardar estado</button></form>}
 <h3>Historial de estados</h3>{history.length===0&&<p>Sin historial registrado; puede ser un incidente anterior a la migración.</p>}{history.map(h=><article key={h.id}><p>{h.previous_status||'Creación'} → {h.status} · {h.author} · {new Date(h.created_at).toLocaleString()}</p><p>{h.justification}</p></article>)}
 <h3>Acciones de respuesta</h3>{actions.map(a=><article key={a.id}><p>{a.author} · {new Date(a.created_at).toLocaleString()}</p><p>{a.description}</p></article>)}{canEdit&&<form onSubmit={saveAction}><label>Acción realizada<textarea required maxLength={4000} value={action} onChange={e=>setAction(e.target.value)}/></label><button disabled={busy||!action.trim()}>Registrar acción</button></form>}
 <h3>Eventos</h3>{detail.events?.map(e=><p key={e.id}>{e.source}: {e.message} | Criticidad {e.asset_criticality} ({e.asset_criticality_observed===true?'declarada':e.asset_criticality_observed===false?'predeterminada, no observada':'procedencia no registrada'}) <button onClick={()=>showEvidence(e.id)}>Evidencia</button></p>)}{evidence!==null&&<details open><summary>Evidencia y primeras 10 procedencias</summary><pre>{JSON.stringify(evidence,null,2)}</pre></details>}</section>}</>}
 <footer>Laboratorio académico · Las sesiones duran 15 minutos.</footer></main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
