import {lazy,Suspense,useEffect,useState} from 'react';
import {useSession} from './auth/SessionProvider';
import {useRoute} from './navigation';
import {request} from './api';
import Shell from './components/Shell';
import IncidentDrawer from './components/IncidentDrawer';
import {Empty,Loading,Notice,PageTitle} from './components/ui';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Incidents from './pages/Incidents';
import ImportEvents from './pages/ImportEvents';
const Analytics=lazy(()=>import('./AnalyticsDashboard'));
const Evaluation=lazy(()=>import('./Evaluation'));
const MachineLearning=lazy(()=>import('./MachineLearning'));
export default function App(){
 const session=useSession(),route=useRoute();const [refreshKey,setRefreshKey]=useState(0);
 const changed=()=>setRefreshKey(n=>n+1);
 useEffect(()=>{document.getElementById('workspace')?.focus()},[route.path]);
 if(session.state==='restoring')return <div className="session-screen"><Loading text="Verificando sesión con la API…"/></div>;
 if(session.state==='unavailable')return <div className="session-screen"><Notice tone="error">{session.message}<button onClick={()=>void session.restore()}>Reintentar verificación</button></Notice></div>;
 if(session.state!=='ready'||!session.user)return <Login/>;
 const user=session.user,writer=user.role!=='observador',researcher=user.role==='administrador';
 const incident=route.search.get('incident');
 const openDetail=(id:string)=>route.setQuery({incident:id});
 return <Shell route={route}><Suspense fallback={<Loading text="Abriendo sección…"/>}>
 {!route.valid?<Empty title="Página no encontrada"><a href="#/dashboard">Volver al resumen</a></Empty>:
 route.path==='dashboard'?<Dashboard refreshKey={refreshKey} onDetail={openDetail}/>:
 route.path==='incidents'?<Incidents route={route} refreshKey={refreshKey} onDetail={openDetail}/>:
 route.path==='analytics'?<Analytics route={route} refreshKey={refreshKey}/>:
 route.path==='import'?(writer?<ImportEvents onImported={changed}/>:<Notice tone="error">HTTP 403 · Solo administrador y analista pueden importar eventos.</Notice>):
 route.path==='evaluation'?<><PageTitle eyebrow="INVESTIGACIÓN" title="Evaluación experimental" description="Compare estrategias bajo las mismas condiciones y conserve resultados reproducibles."/><Evaluation researcher={researcher} request={request}/></>:
 <><PageTitle eyebrow="MODELOS EXPERIMENTALES" title="Machine learning" description="Consulte versiones e inferencias. Weighted-v2 continúa como motor operativo predeterminado."/><MachineLearning researcher={researcher} request={request}/></>}
 </Suspense>{incident&&(/^[0-9a-f-]{36}$/i.test(incident)?<IncidentDrawer key={incident} id={incident} user={user} onChanged={changed} onClose={()=>route.setQuery({incident:null},true)}/>:<Notice tone="error">Identificador de incidente inválido.</Notice>)}</Shell>;
}
