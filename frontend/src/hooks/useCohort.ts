import {useEffect,useMemo,useState} from 'react';
import {request} from '../api';
import {initialFilters,parameters} from '../components/IncidentFilters';
import type {Dashboard,Filters} from '../types';
import type {Route} from '../navigation';
export function useCohort(route:Route,refreshKey:number,limit=50){
 const key=['start','end','time_basis','priority','event_type','status','assignee','source'].map(k=>`${k}=${route.search.get(k)??''}`).join('&');
 const filters=useMemo(()=>initialFilters(route.search),[key]);
 const rawPage=Number(route.search.get('page')??0),page=Number.isInteger(rawPage)&&rawPage>=0&&rawPage<=2000?rawPage:0;
 const query=parameters(filters).toString()+`&offset=${page*limit}&limit=${limit}`;
 const [data,setData]=useState<Dashboard|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{let active=true;setLoading(true);setError('');request('/api/analytics/dashboard?'+query).then(d=>{if(active)setData(d)}).catch(e=>{if(active){setError(String(e));setData(null)}}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[query,refreshKey]);
 function apply(value:Filters){route.setQuery({...value,page:null})}
 return {filters,page,data,loading,error,apply};
}
