import {ReactNode,useId} from 'react';
export function Notice({children,tone='info'}:{children:ReactNode;tone?:'info'|'error'|'success'|'warning'}){
 return <div className={`notice ${tone}`} role={tone==='error'?'alert':'status'}>{children}</div>;
}
export function Loading({text='Consultando datos…'}:{text?:string}){return <div className="loading" role="status"><span className="spinner"/>{text}</div>}
export function Empty({title,children}:{title:string;children?:ReactNode}){return <div className="empty"><span className="empty-symbol" aria-hidden="true">◇</span><h3>{title}</h3>{children&&<p>{children}</p>}</div>}
export function Badge({children,kind}:{children:ReactNode;kind?:string}){return <span className={`badge badge-${kind??String(children).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/ /g,'-')}`}>{children}</span>}
export function Tabs({value,onChange,items}:{value:string;onChange:(s:string)=>void;items:{id:string;label:string}[]}){
 const id=useId();
 return <div className="tabs" role="tablist" aria-label="Secciones del contenido">{items.map((item,i)=><button id={`${id}-${item.id}`} role="tab" aria-selected={value===item.id} tabIndex={value===item.id?0:-1} key={item.id} onClick={()=>onChange(item.id)} onKeyDown={e=>{
  const next=e.key==='ArrowRight'?(i+1)%items.length:e.key==='ArrowLeft'?(i-1+items.length)%items.length:e.key==='Home'?0:e.key==='End'?items.length-1:-1;
  if(next>=0){e.preventDefault();onChange(items[next].id);document.getElementById(`${id}-${items[next].id}`)?.focus()}
 }}>{item.label}</button>)}</div>;
}
export function JsonViewer({value,label='Datos técnicos'}:{value:unknown;label?:string}){
 const text=typeof value==='string'?value:JSON.stringify(value,null,2);
 return <details className="json-viewer"><summary>{label}</summary><pre tabIndex={0}>{text}</pre></details>;
}
export function PageTitle({eyebrow,title,description,action}:{eyebrow:string;title:string;description:string;action?:ReactNode}){
 return <div className="page-title"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}
export const date=(s:string)=>new Intl.DateTimeFormat('es-MX',{dateStyle:'medium',timeStyle:'short',timeZone:'America/Mexico_City'}).format(new Date(s));
