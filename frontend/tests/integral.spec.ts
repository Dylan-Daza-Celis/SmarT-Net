import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('recorrido real con tres roles, filtros, acciones, errores y reportes',async({page,browser,baseURL})=>{
 const credentials=JSON.parse(process.env.VALIDATION_CREDENTIALS!);
 const prefix=process.env.VALIDATION_OUTPUT!;
 const checks:string[]=[];
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.name));
 // No requests may escape to the user's usual API or an external target.
 await page.route('**/*',route=>{const url=new URL(route.request().url());return url.origin===baseURL?route.continue():route.abort()});
 async function login(role:string){
  await page.goto('/');
  await page.getByLabel('Usuario',{exact:true}).fill(credentials[role][0]);
  await page.getByLabel('Contraseña',{exact:true}).fill(credentials[role][1]);
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Dashboard analítico',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Aplicar filtros',exact:true})).toBeEnabled();
  checks.push('login '+role);
 }
 async function period(){
  await page.getByLabel('Desde UTC (incluido)').fill('2026-01-01T00:00');
  await page.getByLabel('Hasta UTC (excluido)').fill('2026-01-02T00:00');
  await page.getByLabel('Eje temporal').selectOption('event_timestamp');
  await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
  await expect(page.getByText('4 incidentes · Página 1',{exact:true})).toBeVisible();
 }
 await page.goto('/');
 await page.getByLabel('Usuario',{exact:true}).fill('missing');
 await page.getByLabel('Contraseña',{exact:true}).fill('wrong');
 await page.getByRole('button',{name:'Entrar',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Credenciales inválidas');
 checks.push('401 visible en formulario de login');
 await login('administrador');await period();
 await expect(page.getByText('No calculable',{exact:false}).first()).toBeVisible();
 await page.screenshot({path:prefix+'.dashboard.png',fullPage:false});
 checks.push('dashboard real, UTC y No calculable');
 await page.getByLabel('Fuente exacta').fill('SOURCE-WITH-NO-EVENTS');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await expect(page.getByText('No hay incidentes para estos filtros.')).toBeVisible();
 await page.getByLabel('Fuente exacta').fill('');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await expect(page.getByText('4 incidentes · Página 1',{exact:true})).toBeVisible();
 checks.push('filtros combinables y estado vacío');
 // Upload a REAL file-shaped buffer; synthetic event is outside the displayed period.
 const smartir={events:[{source:'ITER10-BROWSER-SYNTHETIC',event_timestamp:'2026-02-01T00:01:00Z',event_type:'escaneo',severity:20,asset_criticality:50,message:'Synthetic browser test'}]};
 await page.locator('input[type=file]').first().setInputFiles({name:'synthetic.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(smartir))});
 await expect(page.getByRole('heading',{name:'Resultado de importación'})).toBeVisible();
 await expect(page.getByText(/Importados: 1 \| Duplicados: 0/)).toBeVisible();
 await page.getByLabel(/^Formato/).selectOption('eve');
 await page.getByLabel('Sensor declarado').fill('iter10-browser');
 const eve={timestamp:'2026-02-01T00:02:00Z',event_type:'alert',src_ip:'192.0.2.88',dest_ip:'198.51.100.88',alert:{signature:'SYNTHETIC BROWSER ONLY',signature_id:1000011,category:'network-scan',severity:3}};
 await page.locator('input[type=file]').first().setInputFiles({name:'synthetic.eve.jsonl',mimeType:'application/x-ndjson',buffer:Buffer.from(JSON.stringify(eve)+'\n')});
 await expect(page.getByText(/Importados: 1 \| Duplicados: 0/)).toBeVisible();
 checks.push('importación SmartIR y Suricata mediante selector de archivos');
 // Filter one unassigned incident, assign it and exercise real forms.
 await page.getByLabel(/^Estado/).selectOption('Nuevo');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await page.getByRole('button',{name:'Detalle',exact:true}).first().click();
 const detail=page.locator('section.panel').filter({has:page.getByRole('button',{name:'Cerrar detalle',exact:true})});
 await expect(detail.getByRole('heading',{name:'Responsabilidad y ciclo de vida'})).toBeVisible();
 await detail.getByLabel(/^Responsable/).selectOption({label:credentials.analista[0]+' · analista'});
 await detail.getByLabel('Justificación de asignación').fill('Asignación sintética por navegador');
 await detail.getByRole('button',{name:'Asignar / reasignar / retirar'}).click();
 await expect(detail.getByRole('heading',{name:/· Asignado/})).toBeVisible();
 await detail.getByLabel('Nuevo estado').selectOption('En análisis');
 await detail.getByLabel('Justificación de transición o reapertura').fill('Análisis sintético por navegador');
 await detail.getByRole('button',{name:'Guardar transición'}).click();
 await expect(detail.getByRole('heading',{name:/· En análisis/})).toBeVisible();
 await expect(detail.getByText(/^Revisión 3 · Ciclo/)).toBeVisible();
 await detail.getByLabel(/^Descripción/).fill('Acción sintética registrada desde Chromium');
 const actionResponse=page.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST');
 await detail.getByRole('button',{name:'Registrar acción sin ejecutar comandos'}).click();
 expect((await actionResponse).status()).toBe(201);
 await expect(detail.locator('article').filter({hasText:'Acción sintética registrada desde Chromium'}).first()).toBeVisible();
 await detail.screenshot({path:prefix+'.incidente.png'});
 checks.push('detalle, asignación, transición, acción y timeline');
 // Stale revision from a second authenticated HTTP writer while this form stays open.
 const auth=await page.request.post('/api/auth/login',{data:{username:credentials.administrador[0],password:credentials.administrador[1]}});
 const token=(await auth.json()).access_token;
 const headers={Authorization:'Bearer '+token};
 const list=await (await page.request.get('/api/incidents',{headers})).json();
 const incident=list.find((i:any)=>i.status==='En análisis'&&i.id!==process.env.VALIDATION_INCIDENT);
 expect(incident).toBeTruthy();
 expect((await page.request.post(`/api/incidents/${incident.id}/actions`,{headers,data:{description:'Second concurrent synthetic writer',expected_revision:incident.revision}})).status()).toBe(201);
 await detail.getByLabel(/^Descripción/).fill('Stale action must be rejected');
 await detail.getByRole('button',{name:'Registrar acción sin ejecutar comandos'}).click();
 await expect(detail.getByRole('alert')).toContainText('Revisión obsoleta');
 checks.push('409 visible por revisión obsoleta real');
 await page.getByRole('button',{name:'Cerrar detalle',exact:true}).click();
 await page.getByLabel(/^Estado/).selectOption('');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'Guardar snapshot y descargar JSON'}).click();
 const downloaded=await download;
 await downloaded.saveAs(prefix+'.reporte.json');
 await page.getByText('Snapshots guardados (archivo independiente de los filtros actuales)',{exact:true}).click();
 for(const format of ['CSV','PDF']){
  const waiting=page.waitForEvent('download');
  await page.getByRole('button',{name:'Descargar '+format,exact:true}).first().click();
  await (await waiting).saveAs(prefix+'.reporte.'+format.toLowerCase());
 }
 checks.push('descargas JSON, CSV y PDF desde botones');
 await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();
 await login('analista');
 await expect(page.getByLabel(/^Formato/)).toBeVisible();
 await expect(page.getByRole('button',{name:'Entrenar y comparar',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Generar dataset',exact:true})).toHaveCount(0);
 checks.push('analista escritor sin entrenamiento ni etiquetas');
 await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();
 await login('observador');await period();
 await expect(page.getByLabel(/^Formato/)).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Guardar snapshot y descargar JSON'})).toHaveCount(0);
 await page.getByRole('button',{name:'Detalle',exact:true}).first().click();
 await expect(page.getByRole('heading',{name:'Línea temporal auditable'})).toBeVisible();
 for(const name of ['Guardar transición','Asignar / reasignar / retirar','Registrar acción sin ejecutar comandos'])await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
 checks.push('observador solo lectura, detalle y timeline');
 // Actual API errors through browser networking, no mocked responses or token captures.
 const statuses=await page.evaluate(async creds=>{
  const login=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:creds[0],password:creds[1]})});
  const t=(await login.json()).access_token;
  const unauth=await fetch('/api/incidents');
  const denied=await fetch('/api/events/import',{method:'POST',headers:{Authorization:'Bearer '+t,'Content-Type':'application/json'},body:'{"events":[]}'});
  const invalid=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'missing',password:'ITER10-NO-ECHO'.repeat(30)})});
  const safe=!(await invalid.text()).includes('ITER10-NO-ECHO');
  let limited:Response|undefined;
  for(let i=0;i<22;i++){
   const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"username":"missing","password":"wrong"}'});
   if(r.status===429){limited=r;break}
   if(r.status!==401)throw Error('Unexpected login status');
  }
  return {unauth:unauth.status,denied:denied.status,invalid:invalid.status,safe,limited:limited?.status,retry:limited?.headers.get('Retry-After')};
 },credentials.observador);
 expect(statuses).toMatchObject({unauth:401,denied:403,invalid:422,safe:true,limited:429});
 expect(Number(statuses.retry)).toBeGreaterThan(0);
 checks.push('401/403/422/429 reales; validación sin reflejar entrada; Retry-After');
 await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();
 await page.getByLabel('Usuario',{exact:true}).fill('missing');
 await page.getByLabel('Contraseña',{exact:true}).fill('wrong');
 await page.getByRole('button',{name:'Entrar',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Retry-After');
 await page.getByLabel('Contraseña',{exact:true}).fill('');
 checks.push('429 visible en formulario, con Retry-After');
 expect(errors).toEqual([]);
 fs.writeFileSync(prefix+'.browser.json',JSON.stringify({browser:browser.version(),engine:'Chromium',checks,statuses,page_errors:errors,
  synthetic:true,network:'real loopback API via same-origin Vite proxy',traces:false,credentials_saved:false},null,2)+'\n');
});
