import {useEffect, useState} from 'react';

type Metric={value:number|null;unit:string;status:string;reason:string|null};
type Dataset={id:string;name:string;data_kind:string};
type Experiment={id:string;configuration:{execution_kind:string;effective_budget:number;cohort_size:number};results?:{
 classification:{accuracy:Metric;matrix:number[][]|null;classes:string[];per_class:Record<string,{support:number;precision:Metric;recall:Metric;f1:Metric}>;macro:Record<string,Metric>};
 binary:{rate:Metric;definition:string};timing:Record<string,Metric>;strategies:Record<string,Record<string,Metric>>;limitations:string[];
}};
type Props={token:string;researcher:boolean;request:(path:string,init?:RequestInit)=>Promise<any>};
const show=(m?:Metric)=>!m||m.value===null?'No calculable':`${Number(m.value.toFixed(4))} ${m.unit}`;

export default function Evaluation({token,researcher,request}:Props){
 const [datasets,setDatasets]=useState<Dataset[]>([]),[runs,setRuns]=useState<{id:string}[]>([]);
 const [dataset,setDataset]=useState(''),[seed,setSeed]=useState(202605),[count,setCount]=useState(60),[budget,setBudget]=useState(10);
 const [result,setResult]=useState<Experiment|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [offsets,setOffsets]=useState({datasets:0,runs:0}),[more,setMore]=useState(false);
 async function load(){try{const [d,r]=await Promise.all([request('/api/evaluation/datasets?limit=50'),request('/api/evaluation/experiments?limit=50')]);setDatasets(d);setRuns(r);setOffsets({datasets:d.length,runs:r.length});setMore(d.length===50||r.length===50);if(!dataset&&d.length)setDataset(d[0].id)}catch(e){setError(String(e))}}
 async function loadMore(){try{const [d,r]=await Promise.all([request(`/api/evaluation/datasets?limit=50&offset=${offsets.datasets}`),request(`/api/evaluation/experiments?limit=50&offset=${offsets.runs}`)]);setDatasets(p=>[...new Map([...p,...d].map(v=>[v.id,v])).values()]);setRuns(p=>[...new Map([...p,...r].map(v=>[v.id,v])).values()]);setOffsets({datasets:offsets.datasets+d.length,runs:offsets.runs+r.length});setMore(d.length===50||r.length===50)}catch(e){setError(String(e))}}
 useEffect(()=>{void load()},[]);
 async function generate(){setBusy(true);setError('');try{const d=await request('/api/evaluation/datasets/synthetic',{method:'POST',body:JSON.stringify({seed,count})});setDataset(d.id);await load()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function importFile(file:File){setBusy(true);setError('');try{if(file.size>2*1024*1024)throw Error('Máximo 2 MiB');const body=await file.text();const d=await request('/api/evaluation/datasets/import',{method:'POST',body});setDataset(d.id);await load()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function run(){setBusy(true);setError('');try{setResult(await request('/api/evaluation/experiments',{method:'POST',body:JSON.stringify({dataset_id:dataset,budget})}));await load()}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function open(id:string){try{setResult(await request(`/api/evaluation/experiments/${id}`))}catch(e){setError(String(e))}}
 async function download(format:'json'|'csv'){
  if(!result)return;
  try{const r=await fetch(`http://localhost:8000/api/evaluation/experiments/${result.id}/export?format=${format}`,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw Error(`Descarga: HTTP ${r.status}`);const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=`experiment-${result.id}.${format}`;a.click();URL.revokeObjectURL(url)}catch(e){setError(String(e))}
 }
 const c=result?.results?.classification;
 return <section className="panel"><h2>Evaluación experimental</h2><p>Reproducción offline de una cola disponible, con presupuesto igual en incidentes. No mide trabajo humano ni demuestra mejoras de tiempo.</p>
 {error&&<p className="error" role="alert">{error}</p>}
 {researcher?<><div className="tools"><label>Semilla<input type="number" min={0} max={4294967295} value={seed} onChange={e=>setSeed(Number(e.target.value))}/></label><label>Casos sintéticos<input type="number" min={6} max={500} value={count} onChange={e=>setCount(Number(e.target.value))}/></label><button disabled={busy} onClick={generate}>Generar dataset</button><label className="upload">Importar dataset autorizado<input type="file" accept=".json" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void importFile(f);e.currentTarget.value=''}}/></label></div><p>Importar exige authorized=true y procedencia declarada en el JSON. No incluir datos sin autorización.</p></>:<p>Referencias y resultados contra etiquetas reservados al administrador investigador. Esta vista no revela respuestas a operadores.</p>}
 <div className="tools"><label>Dataset<select value={dataset} onChange={e=>setDataset(e.target.value)}><option value="">Seleccionar</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.name} ({d.data_kind})</option>)}</select></label>{researcher&&<><label>Presupuesto (incidentes)<input type="number" min={0} max={500} value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label><button disabled={busy||!dataset} onClick={run}>Comparar estrategias</button></>}<button onClick={load}>Actualizar evaluaciones</button></div>
 <label>Experimentos guardados<select value={result?.id??''} onChange={e=>{if(e.target.value)void open(e.target.value)}}><option value="">Seleccionar</option>{runs.map(r=><option key={r.id}>{r.id}</option>)}</select></label><button disabled={!more} onClick={loadMore}>Cargar más datasets y experimentos</button>
 {result&&<><p>Experimento {result.id}: {result.configuration.execution_kind}. Cohorte {result.configuration.cohort_size}; presupuesto efectivo {result.configuration.effective_budget}.</p>{result.results&&<>
 <h3>Comparación de selección simulada</h3><table><thead><tr><th>Estrategia</th><th>Cobertura crítica</th><th>Seleccionados</th><th>Pendientes</th><th>Eventos seleccionados</th></tr></thead><tbody>{Object.entries(result.results.strategies).map(([name,s])=><tr key={name}><td>{name}</td>{['critical_coverage','selected','backlog','selected_events'].map(k=><td key={k} title={s[k]?.reason??''}>{show(s[k])}</td>)}</tr>)}</tbody></table>
 <p>Exactitud del clasificador SmartIR (común a ambas colas): {show(c?.accuracy)}. {c?.accuracy.reason}</p><p>FPR: {show(result.results.binary.rate)}. {result.results.binary.rate.reason} {result.results.binary.definition}</p>
 <h3>Matriz de confusión</h3><p>Filas: referencia. Columnas: predicción. FIFO ordena, no predice una clase alternativa.</p>{c?.matrix?<table><thead><tr><th>Real / predicha</th>{c.classes.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{c.matrix.map((row,i)=><tr key={i}><th>{c.classes[i]}</th>{row.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table>:<p>No calculable: faltan referencias completas.</p>}
 <h3>Precisión, recall y F1</h3><table><thead><tr><th>Clase</th><th>Soporte</th><th>Precisión</th><th>Recall</th><th>F1</th></tr></thead><tbody>{Object.entries(c?.per_class??{}).map(([label,v])=><tr key={label}><td>{label}</td><td>{v.support}</td>{[v.precision,v.recall,v.f1].map((m,i)=><td key={i} title={m.reason??''}>{show(m)}</td>)}</tr>)}</tbody></table>{Object.entries(c?.macro??{}).map(([name,m])=><p key={name}>Macro {name}: {show(m)}. {m.reason}</p>)}
 <h3>Tiempos descriptivos del dataset</h3>{Object.entries(result.results.timing).map(([name,m])=><p key={name}>{name.toUpperCase()}: {show(m)}. {m.reason}</p>)}<p>Los tiempos importados son comunes a ambas estrategias; no prueban un efecto causal de ordenar.</p>
 <h3>Limitaciones registradas</h3>{result.results.limitations.map(s=><p key={s}>{s}</p>)}<button onClick={()=>download('json')}>Descargar JSON</button> <button onClick={()=>download('csv')}>Descargar CSV</button></>}{!result.results&&<details><summary>Órdenes sin referencias</summary><pre>{JSON.stringify(result,null,2)}</pre></details>}</>}
 </section>
}
