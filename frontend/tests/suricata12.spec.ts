import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('EVE offline: criticidad de alerta y activo separadas, consulta por rol',async({page,browser,baseURL})=>{
 const credentials=JSON.parse(process.env.VALIDATION_CREDENTIALS!);
 const prefix=process.env.VALIDATION_OUTPUT!;
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.name));
 await page.route('**/*',route=>new URL(route.request().url()).origin===baseURL?route.continue():route.abort());
 for(const role of ['analista','observador']){
  await page.goto('/');
  await page.getByLabel('Usuario',{exact:true}).fill(credentials[role][0]);
  await page.getByLabel('Contraseña',{exact:true}).fill(credentials[role][1]);
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Dashboard analítico',exact:true})).toBeVisible();
  await page.getByLabel('Desde UTC (incluido)').fill('2026-01-01T00:00');
  await page.getByLabel('Hasta UTC (excluido)').fill('2026-01-02T00:00');
  await page.getByLabel('Eje temporal').selectOption('event_timestamp');
  await page.getByLabel('Tipo de incidente',{exact:true}).fill('prueba_icmp');
  await page.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
  await expect(page.getByText('1 incidentes · Página 1',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Detalle',exact:true}).click();
  const detail=page.locator('section.panel').filter({has:page.getByRole('button',{name:'Cerrar detalle',exact:true})});
  const normalization=detail.locator('.event-normalization').first();
  await expect(normalization).toContainText('Prioridad Suricata original: 3 (ordinal; 1 es mayor prioridad, no porcentaje)');
  await expect(normalization).toContainText('Criticidad de la alerta derivada: 40/100 · Media');
  await expect(normalization).toContainText('SMARTIR WSL2 LAB ICMP TEST · SID: 9900012');
  await expect(normalization).toContainText('No demuestra DoS');
  await expect(normalization.locator('..')).toContainText('Criticidad del activo 50 (predeterminada, no observada)');
  await expect(normalization).toContainText('suricata-eve-v2');
  if(role==='analista')await normalization.locator('..').screenshot({path:prefix+'.evento.png'});
  if(role==='observador'){
   await expect(page.getByLabel(/^Formato/)).toHaveCount(0);
   await expect(detail.getByRole('button',{name:'Guardar transición'})).toHaveCount(0);
   await expect(detail.getByRole('button',{name:'Asignar / reasignar / retirar'})).toHaveCount(0);
  }
  await page.getByRole('button',{name:'Cerrar sesión',exact:true}).click();
 }
 expect(errors).toEqual([]);
 fs.writeFileSync(prefix+'.browser.json',JSON.stringify({browser:browser.version(),roles:['analista','observador'],
  checks:['filtro prueba_icmp y UTC','prioridad original 3, índice 40 Media, activo 50 no observado',
  'firma y SID preservados','aviso de prueba declarada','observador sin controles de escritura'],
  page_errors:errors,source:'Suricata engine from synthetic offline PCAP',live_capture:false,
  network:'real loopback API, no mocked responses',credentials_saved:false,traces:false},null,2)+'\n');
});
