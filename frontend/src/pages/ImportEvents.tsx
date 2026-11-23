import {FormEvent,useState} from 'react';
import {apiResponse,checkResponse,request} from '../api';
import {PageTitle,Notice,JsonViewer} from '../components/ui';
type Report={imported:number;duplicates:number;discarded?:number;unknown?:number;batches?:number;complete?:boolean;errors?:{line:number|null;code:string;fields:string[]}[];errors_omitted?:number};
export default function ImportEvents({onImported}:{onImported:()=>void}){
 const [format,setFormat]=useState('smartir'),[sensor,setSensor]=useState('suricata'),[file,setFile]=useState<File|null>(null),[report,setReport]=useState<Report|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function submit(e:FormEvent){e.preventDefault();if(!file)return;setBusy(true);setError('');setReport(null);
  try{
   if(file.size>10*1024*1024)throw Error('El archivo supera 10 MiB');
   let result:Report;
   if(format==='eve'){
    const response=await apiResponse(`/api/events/import/eve?filename=${encodeURIComponent(file.name)}&sensor_id=${encodeURIComponent(sensor)}`,{method:'POST',headers:{'Content-Type':'application/x-ndjson'},body:file});
    if(response.status!==413)await checkResponse(response);
    result=await response.json();
    if(!response.ok)setError('Se alcanzaron los límites; el reporte indica los lotes conservados.');
   }else{
    const text=await file.text();const parsed=file.name.endsWith('.jsonl')?text.split(/\r?\n/).filter(Boolean).map(x=>JSON.parse(x)):JSON.parse(text);
    result=await request('/api/events/import',{method:'POST',body:JSON.stringify(Array.isArray(parsed)?{events:parsed}:parsed)});
   }
   setReport(result);onImported();
   if(result.complete===false)setError('Importación parcial por límite; revise el reporte antes de continuar.');
  }catch(e){setError(String(e instanceof Error?e.message:e))}finally{setBusy(false)}
 }
 return <><PageTitle eyebrow="INGESTIÓN AUTORIZADA" title="Importación de eventos" description="Incorpore eventos SmartIR o EVE JSON Lines. Las repeticiones se deduplican con su fingerprint y conservan procedencia."/>
 <div className="import-grid"><section className="panel"><h2>Preparar una importación</h2><form onSubmit={submit}>
 <label>Formato<select disabled={busy} value={format} onChange={e=>{setFormat(e.target.value);setReport(null)}}><option value="smartir">SmartIR JSON / JSONL</option><option value="eve">Suricata EVE JSON Lines</option></select></label>
 {format==='eve'&&<label>Sensor declarado<input value={sensor} onChange={e=>setSensor(e.target.value)} maxLength={80} pattern="[a-zA-Z0-9_.:-]+" required disabled={busy}/></label>}
 <label className="file-picker">Archivo de eventos<input type="file" accept=".json,.jsonl,.ndjson" required disabled={busy} onChange={e=>{setFile(e.target.files?.[0]??null);setReport(null)}}/></label>
 {file&&<p className="muted">{file.name} · {(file.size/1024).toFixed(1)} KiB · Se enviará al confirmar.</p>}
 <button disabled={busy||!file}>{busy?'Procesando archivo…':'Importar archivo'}</button></form></section>
 <aside className="panel import-help"><span className="eyebrow">ANTES DE IMPORTAR</span><h2>Preserve la procedencia</h2><p>Use un identificador estable para el mismo sensor. Cambiarlo altera la identidad de los eventos.</p><p>EVE: UTF-8, un objeto por línea, máximo 10 MiB, 64 KiB por línea y 10.000 registros. Solo se importan alertas.</p><p>SmartIR: JSON normalizado; el backend limita el cuerpo a 5 MiB. No se ejecutan comandos ni acciones de red.</p><Notice tone="warning">Las pruebas ICMP declaradas no demuestran un ataque. Los datos de laboratorio deben identificarse como tales.</Notice></aside></div>
 {error&&<Notice tone="error">{error}</Notice>}{report&&<section className="panel" aria-live="polite"><h2>Resultado de importación</h2><Notice tone={report.complete===false?'warning':'success'}>{report.complete===false?'Se conservaron los lotes aceptados. Revise los errores.':'La API confirmó el procesamiento del archivo.'}</Notice><div className="kpi-grid compact">{[['Importados',report.imported],['Duplicados',report.duplicates],['Descartados',report.discarded??0],['Desconocidos',report.unknown??0]].map(([label,n])=><article className="kpi" key={label}><span>{label}</span><strong>{n}</strong></article>)}</div><p>Importados: {report.imported} | Duplicados: {report.duplicates} | Descartados: {report.discarded??0} | Desconocidos: {report.unknown??0} | Lotes: {report.batches??1}</p>{report.errors?.map((e,i)=><Notice key={i} tone="warning">Línea {e.line??'-'}: {e.code} {e.fields.join(', ')}</Notice>)}{!!report.errors_omitted&&<p>Errores adicionales omitidos: {report.errors_omitted}</p>}<JsonViewer value={report} label="Reporte completo de la API"/><a className="text-link" href="#/incidents">Consultar incidentes →</a></section>}</>;
}
