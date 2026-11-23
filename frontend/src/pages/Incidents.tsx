import type {Route} from '../navigation';
import {useCohort} from '../hooks/useCohort';
import IncidentFilters from '../components/IncidentFilters';
import IncidentTable from '../components/IncidentTable';
import {PageTitle,Notice,Loading} from '../components/ui';
export default function Incidents({route,refreshKey,onDetail}:{route:Route;refreshKey:number;onDetail:(id:string)=>void}){
 const {filters,page,data,loading,error,apply}=useCohort(route,refreshKey);
 return <><PageTitle eyebrow="GESTIÓN OPERATIVA" title="Incidentes" description="Explore la cola de trabajo y abra cada caso sin perder sus filtros."/>
 <section className="panel"><div className="section-heading"><h2>Filtros de la cola</h2><span className="muted">Intervalo UTC · inicio incluido, fin excluido</span></div><IncidentFilters value={filters} onApply={apply} busy={loading}/></section>
 <section className="panel table-panel"><div className="section-heading"><h2>Incidentes de la cohorte</h2><span className="muted">{data?.incidents.total??'…'} registros</span></div>{error&&<Notice tone="error">{error}</Notice>}{loading?<Loading/>:data&&<><IncidentTable items={data.incidents.items} onDetail={onDetail}/><div className="pagination"><span>{data.incidents.total} incidentes · Página {page+1}</span><div><button className="button-secondary" disabled={page===0} onClick={()=>route.setQuery({page:String(page-1)})}>Anterior</button><button className="button-secondary" disabled={(page+1)*50>=data.incidents.total} onClick={()=>route.setQuery({page:String(page+1)})}>Siguiente</button></div></div></>}<p className="section-footnote">Prioridad, estado y responsable actuales. Los eventos coincidentes se deduplican; no se cuentan líneas repetidas como eventos nuevos.</p></section></>;
}
