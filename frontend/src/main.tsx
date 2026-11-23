import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import Evaluation from './Evaluation';
import MachineLearning from './MachineLearning';
import IncidentLifecycle from './IncidentLifecycle';
import AnalyticsDashboard from './AnalyticsDashboard';
import SuricataEventDetails from './SuricataEventDetails';
import {API} from './api';
type User = {id:string; username:string; role:'administrador'|'analista'|'observador'; eve_only?:boolean};
type ImportReport = {imported:number;duplicates:number;discarded?:number;unknown?:number;batches?:number;complete?:boolean;errors?:{line:number|null;code:string;fields:string[]}[];errors_omitted?:number};
type EventView = {id:string;source:string;message:string;severity:number;asset_criticality:number;asset_criticality_observed:boolean|null;adapter_metadata:Record<string,unknown>|null};
type Incident = {id:string; created_at:string; revision:number; assigned_to_id:string|null; assignee:{id:string;username:string;active:boolean}|null; needs_review:boolean; event_type:string; destination_ip:string|null; status:string; score:number; priority:string; event_count:number; explanation:{algorithm_version?:string; factors?:Record<string,{value:number;weight:number;contribution:number;observed:boolean;basis?:string}>; context?:{known:boolean;policy:string}}; events_offset:number; events_limit:number; events?:EventView[]};
const statuses = ['Nuevo','Asignado','En análisis','En respuesta','Resuelto','Cerrado'];
function App(){
 const [format,setFormat]=useState('smartir'),[sensor,setSensor]=useState('suricata'),[report,setReport]=useState<ImportReport|null>(null),[evidence,setEvidence]=useState<unknown>(null);
 const [refreshKey,setRefreshKey]=useState(0);
 const [token,setToken]=useState(''), [user,setUser]=useState<User|null>(null);
 const [username,setUsername]=useState(''), [password,setPassword]=useState('');
 const [detail,setDetail]=useState<Incident|null>(null);
 const [error,setError]=useState(''), [busy,setBusy]=useState(false);
 const canEdit=user?.role==='administrador'||user?.role==='analista';
 function logout(){setToken('');setUser(null);setDetail(null);setPassword('');setReport(null);setEvidence(null)}
 async function request(path:string, init:RequestInit={}, access=token){
  const r=await fetch(API+path,{...init,headers:{'Content-Type':'application/json',...(access?{Authorization:`Bearer ${access}`}:{})}});
  if(!r.ok){if(r.status===401 && access)logout();const body=await r.json().catch(()=>({detail:'API no disponible'}));throw new Error((typeof body.detail==='string'?body.detail:JSON.stringify(body.detail))+(r.status===429?' Retry-After: '+(r.headers.get('Retry-After')??'?')+' s':''))}
  return r.json();
 }
 async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const data=await request('/api/auth/login',{method:'POST',body:JSON.stringify({username,password})},'');const me=await request('/api/auth/me',{},data.access_token);if(me.eve_only){setPassword('');throw new Error('Cuenta exclusiva del agente EVE; no dispone de acceso interactivo.')}setUser(me);setToken(data.access_token);setPassword('')}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function load(){setRefreshKey(n=>n+1)}
 async function download(path:string){const r=await fetch(API+path,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok){if(r.status===401)logout();throw new Error('No se pudo descargar: '+r.status)}const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=r.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'smartir-report';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 useEffect(()=>{if(token)void load()},[token]);
 async function openDetail(id:string,eventsOffset=0){setDetail(null);setEvidence(null);setError('');try{setDetail(await request(`/api/incidents/${id}?events_offset=${eventsOffset}&events_limit=100`))}catch(e){setError(String(e))}}
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
 <AnalyticsDashboard request={request} download={download} writer={canEdit} researcher={user.role==='administrador'} refreshKey={refreshKey} onDetail={id=>void openDetail(id)}/>
 <section className="panel"><div className="tools"><h2>Importación de eventos</h2>{canEdit&&<><label>Formato<select disabled={busy} value={format} onChange={e=>setFormat(e.target.value)}><option value="smartir">SmartIR JSON / JSONL</option><option value="eve">Suricata EVE JSON Lines</option></select></label>{format==='eve'&&<label>Sensor declarado<input value={sensor} maxLength={80} pattern="[a-zA-Z0-9_.:-]+" required onChange={e=>setSensor(e.target.value)}/></label>}<label className="upload">{busy?'Importando...':'Importar archivo'}<input disabled={busy} type="file" accept=".json,.jsonl,.ndjson" onChange={e=>{const f=e.target.files?.[0];if(f)void importFile(f);e.currentTarget.value=''}}/></label></>}</div>{report&&<section aria-live="polite"><h3>Resultado de importación</h3><p>Importados: {report.imported} | Duplicados: {report.duplicates} | Descartados: {report.discarded??0} | Desconocidos: {report.unknown??0} | Lotes: {report.batches??1}</p>{report.errors?.map((e,index)=><p key={index} className="error">Línea {e.line??'-'}: {e.code} {e.fields.join(', ')}</p>)}{!!report.errors_omitted&&<p>Errores adicionales omitidos: {report.errors_omitted}</p>}</section>}</section>
 <MachineLearning token={token} researcher={user.role==='administrador'} request={request}/><Evaluation token={token} researcher={user.role==='administrador'} request={request}/>
 {detail&&<section className="panel"><div className="tools"><h2>{detail.event_type} · {detail.status}</h2><button onClick={()=>setDetail(null)}>Cerrar detalle</button></div><p>Destino: {detail.destination_ip??'No indicado'}</p><p>Riesgo: {detail.score}/100 | {detail.priority}</p>{detail.explanation.factors?<><p>Algoritmo: {detail.explanation.algorithm_version}</p><table><thead><tr><th>Factor</th><th>Valor</th><th>Peso</th><th>Aporte</th></tr></thead><tbody>{Object.entries(detail.explanation.factors).map(([name,f])=><tr key={name}><td>{name}{f.basis?` (${f.basis})`:!f.observed?' (valor de política, no observado)':''}</td><td>{f.value}</td><td>{f.weight*100}%</td><td>{f.contribution}</td></tr>)}</tbody></table><p>Contexto desconocido: valor de política {detail.explanation.factors.context?.value}; no es un dato observado.</p></>:<p>Evaluación heredada: versión y parámetros originales no registrados.</p>}<details><summary>Explicación completa</summary><pre>{JSON.stringify(detail.explanation,null,2)}</pre></details>
 <p>Responsable: {detail.assignee?.username??'Sin responsable'}</p><IncidentLifecycle incident={detail} user={user} request={request} onChanged={async()=>{await openDetail(detail.id);await load()}}/>
 <h3>Eventos</h3><p>{detail.events_offset+1} - {detail.events_offset+(detail.events?.length??0)} / {detail.event_count}</p><button disabled={detail.events_offset===0} onClick={()=>void openDetail(detail.id,Math.max(0,detail.events_offset-detail.events_limit))}>Anterior</button><button disabled={detail.events_offset+detail.events_limit>=detail.event_count} onClick={()=>void openDetail(detail.id,detail.events_offset+detail.events_limit)}>Siguiente</button>{detail.events?.map(e=><article key={e.id}><p>{e.source}: {e.message} | Criticidad del activo {e.asset_criticality} ({e.asset_criticality_observed===true?'declarada':e.asset_criticality_observed===false?'predeterminada, no observada':'procedencia no registrada'}) <button onClick={()=>showEvidence(e.id)}>Evidencia</button></p><SuricataEventDetails metadata={e.adapter_metadata} severity={e.severity}/></article>)}{evidence!==null&&<details open><summary>Evidencia y primeras 10 procedencias</summary><pre>{JSON.stringify(evidence,null,2)}</pre></details>}</section>}</>}
 <footer>Laboratorio académico · Las sesiones duran 15 minutos.</footer></main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
