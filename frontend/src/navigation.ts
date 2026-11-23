import {useEffect,useState} from 'react';
const paths=['dashboard','incidents','analytics','import','evaluation','ml'];
function read(){const raw=window.location.hash.slice(1)||'/dashboard';const [path,query='']=raw.split('?');return {path:path.replace(/^\//,''),search:new URLSearchParams(query)}}
export function useRoute(){
 const [route,setRoute]=useState(read);
 useEffect(()=>{const change=()=>setRoute(read());window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change)},[]);
 function setQuery(values:Record<string,string|null>,replace=false){
  const next=new URLSearchParams(route.search);Object.entries(values).forEach(([k,v])=>v===null||v===''?next.delete(k):next.set(k,v));
  const hash=`#/${route.path}${next.size?'?'+next:''}`;
  if(replace){history.replaceState(null,'',hash);window.dispatchEvent(new HashChangeEvent('hashchange'))}else window.location.hash=hash;
 }
 return {...route,valid:paths.includes(route.path),setQuery};
}
export type Route=ReturnType<typeof useRoute>;
