import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs';
import crypto from 'node:crypto';
const credentials=JSON.parse(process.env.VALIDATION_CREDENTIALS!);
const ids=JSON.parse(process.env.VALIDATION_IDS!);
const prefix=process.env.VALIDATION_OUTPUT!;
const checks:string[]=[];
const pageErrors:string[]=[];
test.beforeEach(async({page,baseURL})=>{
 page.on('pageerror',e=>pageErrors.push(e.name));
 await page.route('**/*',route=>new URL(route.request().url()).origin===baseURL?route.continue():route.abort());
});
async function login(page:Page,role='administrador',path='/dashboard'){
 await page.goto('/#'+path);
 await page.getByLabel('Usuario',{exact:true}).fill(credentials[role][0]);
 await page.getByLabel('Contraseña',{exact:true}).fill(credentials[role][1]);
 await page.getByRole('button',{name:'Entrar',exact:true}).click();
 await expect(page.getByRole('button',{name:'Cerrar sesión',exact:true})).toBeVisible();
}
async function incidents(page:Page){
 await page.getByRole('link',{name:'Incidentes',exact:true}).click();
 await page.getByLabel('Desde UTC (incluido)').fill('2026-01-02T00:00');
 await page.getByLabel('Hasta UTC (excluido)').fill('2026-01-03T00:00');
 await page.getByLabel('Eje temporal').selectOption('event_timestamp');
 await page.getByLabel('Tipo de incidente',{exact:true}).fill('prueba_icmp');
 await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
 await expect(page.getByText('1 incidentes · Página 1',{exact:true})).toBeVisible();
}
test('sesión HttpOnly, rutas, filtros, detalle contextual, evidencia y recarga',async({page,context})=>{
 await login(page);await expect(page.getByRole('heading',{name:'Centro de operaciones'})).toBeVisible();
 await expect(page.locator('.kpi')).toHaveCount(6);
 await expect(page.locator('.kpi').filter({has:page.getByText('Incidentes',{exact:true})}).locator('strong')).toHaveText('5');
 await expect(page.locator('.overview-chart .recharts-surface')).toBeVisible();
 await page.screenshot({path:prefix+'.dashboard.png'});
 const cookies=await context.cookies();const cookie=cookies.find(c=>c.name==='smartir_session');
 expect(Boolean(cookie?.httpOnly)).toBe(true);expect(cookie?.sameSite).toBe('Strict');expect(cookie?.path).toBe('/api');
 const storage=await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length,jsCookie:document.cookie.includes('smartir_session')}));
 expect(storage).toEqual({local:0,session:0,jsCookie:false});
 await page.reload();await expect(page.getByRole('heading',{name:'Centro de operaciones'})).toBeVisible();
 await page.getByRole('link',{name:'Incidentes',exact:true}).focus();await page.keyboard.press('Enter');
 await expect(page.getByRole('heading',{name:'Incidentes',exact:true})).toBeVisible();
 await incidents(page);const filtered=page.url();await page.screenshot({path:prefix+'.incidentes.png'});
 await page.getByRole('button',{name:/^Detalle/}).click();
 const drawer=page.getByRole('dialog');await expect(drawer).toBeVisible();
 await expect(drawer.getByText('Prueba de laboratorio declarada.',{exact:false})).toBeVisible();
 await page.reload();await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByRole('tab',{name:'Eventos y evidencias',exact:true}).click();
 const event=page.locator('.event-card').first();await expect(event).toContainText('Prioridad Suricata original: 3');
 await expect(event).toContainText('40/100 · Media');await expect(event).toContainText('Criticidad del activo 50 (predeterminada, no observada)');
 await expect(event).toContainText('SID: 9900013');
 await event.getByRole('button',{name:/^Evidencia/}).click();
 await event.getByText('Registro original EVE / SmartIR',{exact:true}).click();
 await expect(event.locator('pre').first()).toContainText('SMARTIR WSL2 LAB ICMP TEST');
 await expect(event).toContainText('synthetic13.jsonl');
 await page.screenshot({path:prefix+'.evidencia.png'});
 for(let i=0;i<12;i++){await page.keyboard.press('Tab');expect(await page.evaluate(()=>Boolean(document.activeElement?.closest('dialog')))).toBe(true)}
 await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
 expect(page.url()).toBe(filtered);
 await page.getByRole('link',{name:'Analítica y reportes',exact:true}).click();
 await expect(page.locator('.chart-grid .recharts-surface').first()).toBeVisible();
 await page.screenshot({path:prefix+'.analitica.png'});
 await page.getByRole('link',{name:'Incidentes',exact:true}).click();
 await expect(page.getByLabel('Tipo de incidente',{exact:true})).toHaveValue('prueba_icmp');
 await expect(page.getByText('1 incidentes · Página 1',{exact:true})).toBeVisible();
 checks.push('cookie HttpOnly, sin almacenamiento JS, recarga, rutas y filtros preservados, panel y evidencia contextual, teclado/Escape');
});
test('administrador: respuesta, revisión concurrente y módulos separados',async({page,baseURL})=>{
 await login(page);await incidents(page);await page.getByRole('button',{name:/^Detalle/}).click();
 const drawer=page.getByRole('dialog');await drawer.getByRole('tab',{name:'Gestión e historial',exact:true}).click();
 await drawer.getByLabel(/^Responsable/).selectOption({label:credentials.analista[0]+' · analista'});
 await drawer.getByLabel('Justificación de asignación').fill('Asignación sintética iteración13');
 await drawer.getByRole('button',{name:'Asignar / reasignar / retirar'}).click();
 await expect(drawer.getByText('Asignado',{exact:true}).first()).toBeVisible();
 await drawer.getByLabel('Nuevo estado').selectOption('En análisis');
 await drawer.getByLabel('Justificación de transición o reapertura').fill('Análisis sintético iteración13');
 await drawer.getByRole('button',{name:'Guardar transición'}).click();
 await expect(drawer.getByText('En análisis',{exact:true}).first()).toBeVisible();
 const currentResponse=await page.request.get(`/api/incidents/${ids.lab_incident}`);
 expect(currentResponse.status()).toBe(200);
 const current=await currentResponse.json();expect(typeof current.revision).toBe('number');
 expect((await page.request.post(`/api/incidents/${ids.lab_incident}/actions`,{headers:{Origin:baseURL!,'X-SmartIR-CSRF':'1'},data:{description:'Concurrent synthetic writer',expected_revision:current.revision}})).status()).toBe(201);
 await drawer.getByLabel(/^Descripción/).fill('Stale revision rejected');
 await drawer.getByRole('button',{name:'Registrar acción sin ejecutar comandos'}).click();
 await expect(drawer.getByRole('alert')).toContainText('Revisión obsoleta');
 await drawer.getByRole('button',{name:'Recargar detalle y revisión'}).click();
 const lifecycleUrl=`**/api/incidents/${ids.lab_incident}/lifecycle`;
 await page.route(lifecycleUrl,route=>route.abort('failed'));
 await drawer.getByRole('button',{name:'Recargar detalle y revisión'}).click();
 await expect(drawer.getByRole('alert')).toBeVisible();
 await page.unroute(lifecycleUrl);
 await drawer.getByRole('button',{name:'Recargar detalle y revisión'}).click();
 await expect(drawer.getByRole('alert')).toHaveCount(0);
 await drawer.getByLabel(/^Descripción/).fill('Acción confirmada desde Chromium iteración13');
 await drawer.getByRole('button',{name:'Registrar acción sin ejecutar comandos'}).click();
 await drawer.getByRole('tab',{name:'Historial auditable',exact:true}).click();
 await expect(drawer.getByText('Acción confirmada desde Chromium iteración13',{exact:false}).first()).toBeVisible();
 await page.screenshot({path:prefix+'.historial.png'});
 await drawer.getByRole('button',{name:/Cerrar detalle/}).click();
 for(const [nav,heading,file] of [['Importación','Importación de eventos','importacion'],['Evaluación','Evaluación experimental','evaluacion'],['Machine learning','Machine learning','ml']]){
  await page.getByRole('link',{name:nav,exact:true}).click();await expect(page.getByRole('heading',{name:heading,exact:true}).first()).toBeVisible();
  if(file==='evaluacion'){await page.getByLabel('Experimentos guardados').selectOption({index:1});await expect(page.getByRole('heading',{name:'Comparación de selección simulada'})).toBeVisible()}
  if(file==='ml'){await page.getByLabel('Versión guardada').selectOption(ids.ml_run);await expect(page.getByText('Exactitud:',{exact:false}).first()).toBeVisible()}
  await page.screenshot({path:prefix+`.${file}.png`});
 }
 await expect(page.getByRole('button',{name:'Entrenar y comparar',exact:true})).toBeVisible();
 await expect(page.getByLabel(/^Formato/)).toHaveCount(0);await expect(page.getByLabel('Desde UTC (incluido)')).toHaveCount(0);
 checks.push('asignación/transición/acción, conflicto409, fallo de red controlado y recuperación, historial, módulos independientes y permiso administrador');
});
for(const role of ['analista','observador'])test(`${role}: restauración y permisos visibles`,async({page})=>{
 await login(page,role);await page.reload();await expect(page.getByRole('button',{name:'Cerrar sesión'})).toBeVisible();
 await incidents(page);await page.getByRole('button',{name:/^Detalle/}).click();
 const drawer=page.getByRole('dialog');await drawer.getByRole('tab',{name:'Gestión e historial',exact:true}).click();
 if(role==='observador'){
  for(const label of ['Guardar transición','Asignar / reasignar / retirar','Registrar acción sin ejecutar comandos'])await expect(drawer.getByRole('button',{name:label})).toHaveCount(0);
  await expect(drawer.getByRole('heading',{name:'Línea temporal auditable'})).toBeVisible();
 }
 await drawer.getByRole('button',{name:/Cerrar detalle/}).click();await page.getByRole('link',{name:'Machine learning',exact:true}).click();
 await expect(page.getByRole('button',{name:'Entrenar y comparar'})).toHaveCount(0);
 await page.goto('/#/import');
 if(role==='observador')await expect(page.getByRole('alert')).toContainText('HTTP 403');else await expect(page.getByLabel(/^Formato/)).toBeVisible();
 checks.push(`${role}: recarga válida, RBAC y rutas protegidas`);
});
test('responsive, foco y contraste de tokens',async({page})=>{
 await login(page);
 for(const width of [1440,820,390]){
  await page.setViewportSize({width,height:950});
  if(width<=900)await page.getByRole('button',{name:'Abrir menú',exact:true}).click();
  await incidents(page);
  const geometry=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,overflow:Array.from(document.querySelectorAll('*')).map(el=>({tag:el.tagName,class:el.className,left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right})).filter(el=>el.right>innerWidth+1)}));
  if(geometry.width>width)fs.writeFileSync(prefix+`.layout-${width}.json`,JSON.stringify(geometry,null,2));
  expect(geometry.width,`document overflow at width ${width}`).toBeLessThanOrEqual(width);
  await page.getByRole('button',{name:/^Detalle/}).click();
  const box=await page.getByRole('dialog').boundingBox();expect(box!.width).toBeLessThanOrEqual(width);
  await expect(page.getByRole('button',{name:/Cerrar detalle/})).toBeVisible();
  await expect(page.getByRole('dialog').locator('.incident-summary')).toBeVisible();
  if(width===390)await page.screenshot({path:prefix+'.movil.png'});
  await page.keyboard.press('Escape');
  expect(await page.evaluate(()=>document.activeElement?.tagName)).toBe('BUTTON');
 }
 const contrast=(a:string,b:string)=>{const luminance=(s:string)=>{const n=s.match(/../g)!.map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*n[0]+.7152*n[1]+.0722*n[2]};const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
 for(const [a,b] of [['e8eff8','121c2a'],['a9bbce','121c2a'],['63ddc4','121c2a'],['08201d','63ddc4']])expect(contrast(a,b)).toBeGreaterThanOrEqual(4.5);
 checks.push('escritorio1440/tablet820/móvil390 sin overflow de documento; diálogo acotado, foco/Escape; cuatro pares de contraste>=4.5');
});
test('expiración real sin renovación, cierre y errores 422/429 sin secretos',async({page,context,baseURL})=>{
 const now=Math.floor(Date.now()/1000),header=Buffer.from(JSON.stringify({alg:'HS256',typ:'JWT'})).toString('base64url');
 const payload=Buffer.from(JSON.stringify({sub:ids.admin,iat:now,exp:now+5,iss:'smartir-net',aud:'smartir-api'})).toString('base64url');
 const signature=crypto.createHmac('sha256',process.env.VALIDATION_JWT_SECRET!).update(header+'.'+payload).digest('base64url');
 await context.addCookies([{name:'smartir_session',value:header+'.'+payload+'.'+signature,domain:new URL(baseURL!).hostname,path:'/api',httpOnly:true,sameSite:'Strict'}]);
 await page.goto('/#/dashboard');await expect(page.getByRole('heading',{name:'Centro de operaciones'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Iniciar sesión'})).toBeVisible({timeout:12000});
 await login(page);await page.goto('/#/incidents?start=bad');await expect(page.getByRole('alert')).toContainText('HTTP 422');
 await page.getByRole('button',{name:'Cerrar sesión'}).click();await page.reload();await expect(page.getByRole('heading',{name:'Iniciar sesión'})).toBeVisible();
 const statuses=await page.evaluate(async()=>{
  const invalid=await fetch('/api/auth/session',{method:'POST',headers:{'Content-Type':'application/json','X-SmartIR-CSRF':'1'},body:JSON.stringify({username:'missing',password:'SENSITIVE-MARKER-'.repeat(30)})});
  const safe=!(await invalid.text()).includes('SENSITIVE-MARKER');let limited=0,retry='';
  for(let i=0;i<22;i++){const r=await fetch('/api/auth/session',{method:'POST',headers:{'Content-Type':'application/json','X-SmartIR-CSRF':'1'},body:'{"username":"missing","password":"wrong"}'});if(r.status===429){limited=r.status;retry=r.headers.get('Retry-After')??'';break}if(r.status!==401)throw Error('Unexpected login status')}
  return {invalid:invalid.status,safe,limited,retry};
 });
 expect(statuses).toMatchObject({invalid:422,safe:true,limited:429});expect(Number(statuses.retry)).toBeGreaterThan(0);
 checks.push('JWT cinco segundos: expira por reloj real/API, logout persistente,422 validación sin eco y429 real con Retry-After');
});
test.afterAll(async({browser})=>{
 expect(pageErrors).toEqual([]);
 fs.writeFileSync(prefix+'.browser.json',JSON.stringify({browser:browser.version(),engine:'Chromium',cases:6,checks,page_errors:pageErrors,
  synthetic:true,network:'real loopback API via same-origin Vite proxy',traces:false,credentials_saved:false},null,2)+'\n');
});
