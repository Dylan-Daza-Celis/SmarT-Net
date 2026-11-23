type Metadata={signature?:unknown;signature_id?:unknown;suricata_severity?:unknown;adapter_version?:unknown;
 classification?:{taxonomy?:string;reason?:string};alert_criticality?:{value:number;level:string|null;basis:string;policy_version:string}};
export default function SuricataEventDetails({metadata,severity}:{metadata:Record<string,unknown>|null;severity:number}){
 if(!metadata)return null;
 const m=metadata as Metadata,c=m.alert_criticality;
 return <div className="event-normalization">
 <p>Firma: {typeof m.signature==='string'?m.signature:'No proporcionada'} · SID: {typeof m.signature_id==='number'?m.signature_id:'No proporcionado'}</p>
 <p>Prioridad Suricata original: {typeof m.suricata_severity==='number'?m.suricata_severity:'No proporcionada'} (ordinal; 1 es mayor prioridad, no porcentaje).</p>
 <p>{c?'Criticidad de la alerta derivada':'Severidad normalizada heredada'}: {c?.value??severity}/100{c?.level?` · ${c.level}`:''}. Índice de ingeniería, no observación de riesgo ni probabilidad.{c&&!c.level?' Sin nivel atribuible: valor ausente o no estándar.':''}</p>
 {m.classification?.taxonomy==='auxiliary_non_attack'&&<p>Prueba ICMP declarada por firma exacta. No demuestra DoS, escaneo ni otro ataque. El score genérico del incidente conserva la política ponderada existente.</p>}
 {m.classification?.reason&&m.classification.taxonomy==='unclassified'&&<p>Sin clasificación de ataque justificable: {m.classification.reason}.</p>}
 <p>Adaptador: {String(m.adapter_version??'no registrado')}{c?` · Política de alerta: ${c.policy_version}`:''}.</p>
 </div>
}
