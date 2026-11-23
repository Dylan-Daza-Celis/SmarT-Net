import {useEffect,useState} from 'react';
import {request} from '../api';
import {Filters,incidentTypes,statuses} from '../types';
export function initialFilters(search=new URLSearchParams()):Filters{
 // datetime-local displays minutes. Round UP so a newly received case isn't excluded for 59 seconds.
 const end=new Date((Math.floor(Date.now()/60000)+1)*60000),start=new Date(end.getTime()-30*86400000);
 const defaults:Filters={start:start.toISOString().slice(0,16),end:end.toISOString().slice(0,16),time_basis:'incident_created',priority:'',event_type:'',status:'',assignee:'',source:''};
 return Object.fromEntries(Object.entries(defaults).map(([k,v])=>[k,search.get(k)??v])) as Filters;
}
export function parameters(f:Filters){const q=new URLSearchParams();Object.entries(f).forEach(([k,v])=>{if(v)q.set(k,k==='start'||k==='end'?v+':00Z':v)});return q}
export default function IncidentFilters({value,onApply,busy=false}:{value:Filters;onApply:(f:Filters)=>void;busy?:boolean}){
 const [draft,setDraft]=useState(value),[options,setOptions]=useState<{sources:string[];assignees:{id:string;username:string}[]}>({sources:[],assignees:[]});
 useEffect(()=>{setDraft(value)},[JSON.stringify(value)]);
 useEffect(()=>{let active=true;request('/api/analytics/options').then(o=>{if(active)setOptions(o)}).catch(()=>{});return()=>{active=false}},[]);
 const field=(k:keyof Filters,v:string)=>setDraft(d=>({...d,[k]:v}));
 return <form className="filter-grid" onSubmit={e=>{e.preventDefault();onApply(draft)}}>
 <label>Desde UTC (incluido)<input type="datetime-local" required value={draft.start} onChange={e=>field('start',e.target.value)}/></label>
 <label>Hasta UTC (excluido)<input type="datetime-local" required value={draft.end} onChange={e=>field('end',e.target.value)}/></label>
 <label>Eje temporal<select value={draft.time_basis} onChange={e=>field('time_basis',e.target.value)}><option value="incident_created">Creación del incidente</option><option value="event_timestamp">Tiempo del evento</option><option value="received_at">Recepción del evento</option></select></label>
 <label>Prioridad<select value={draft.priority} onChange={e=>field('priority',e.target.value)}><option value="">Todas</option>{['Baja','Media','Alta','Crítica'].map(p=><option key={p}>{p}</option>)}</select></label>
 <label>Tipo de incidente<input list="incident-types" maxLength={60} value={draft.event_type} onChange={e=>field('event_type',e.target.value)}/><datalist id="incident-types">{incidentTypes.map(t=><option key={t} value={t}/>)}</datalist></label>
 <label>Estado<select value={draft.status} onChange={e=>field('status',e.target.value)}><option value="">Todos</option>{statuses.map(s=><option key={s}>{s}</option>)}</select></label>
 <label>Responsable<select value={draft.assignee} onChange={e=>field('assignee',e.target.value)}><option value="">Todos</option><option value="unassigned">Sin responsable</option>{options.assignees.map(u=><option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
 <label>Fuente exacta<input list="incident-sources" maxLength={100} value={draft.source} onChange={e=>field('source',e.target.value)}/><datalist id="incident-sources">{options.sources.map(s=><option key={s} value={s}/>)}</datalist></label>
 <div className="filter-actions"><button disabled={busy}>Aplicar filtros</button><button type="button" className="button-secondary" onClick={()=>onApply(initialFilters())}>Restablecer</button></div>
 </form>;
}
