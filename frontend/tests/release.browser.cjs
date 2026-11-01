/* Saved genuine evidence + actual local UI/API, no paid calls or screenshots. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const path=require('node:path');
const fs=require('node:fs');
const base=process.env.PROOFPORT_INTEGRATION_URL,pack=process.env.PROOFPORT_RELEASE_PACK;
if(process.env.PROOFPORT_RELEASE_SMOKE!=='1'||!/^http:\/\/127\.0\.0\.1:(8001|8765)$/.test(base||'')||!pack) throw Error('Explicit local release smoke and verified pack required');

async function main(){
 const errors=[],external=[];const browser=await chromium.launch({headless:true,
  executablePath:process.env.PROOFPORT_CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--disable-background-networking','--disable-component-update','--no-first-run']});
 try {
  const context=await browser.newContext({acceptDownloads:false});
  await context.route('**/*',async route=>{
   const r=route.request();if(!r.url().startsWith(base+'/')){external.push(r.url());return route.abort();}
   assert.notEqual(r.method(),'POST','Read-only saved-run rehearsal must create no operation');return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.waitForFunction(()=>window.PP&&PP.control.state.mode==='v1');
  const scenarios=[];
  for(const kind of ['python','php','security']){
   const file=path.join(pack,'proofport-'+kind+'.json');assert.ok(fs.existsSync(file));
   await page.locator('input[type=file]').first().setInputFiles(file);
   await page.waitForFunction(k=>{const r=PP.store.state.run;return r&&r.origin==='replay'&&r.report.verification.historical.kind===k&&r.chain?.status==='ok';},kind);
   const p=await page.evaluate(()=>PP.labels.provenance(PP.store.state.run));
   assert.match(p.label,kind==='security'?/rejected \/ needs review/:/Saved real Meta run/);
   for(const width of [1440,390]){
    await page.setViewportSize({width,height:900});
    for(const route of ['overview','migration','security','compatibility','evidence']){
     await page.evaluate(r=>{location.hash='#/'+r;},route);
     await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
     const excess=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
     assert.ok(excess<=1,kind+' '+route+' overflows at '+width+': '+excess);
    }
   }
   const r=await page.evaluate(()=>({status:PP.store.state.run.state.status,chain:PP.store.state.run.chain.status,
     tests_run:PP.store.state.run.report.verification.target_tests.tests_run,
     tests_passed:PP.store.state.run.report.verification.target_tests.outcomes.filter(o=>o.status==='passed').length,
     cases_matched:PP.store.state.run.state.metrics.tests_passed,cases_total:PP.store.state.run.state.metrics.tests_total}));
   assert.equal(r.tests_passed,kind==='security'?0:kind==='php'?9:3);
   assert.equal(r.cases_matched,kind==='security'?5:kind==='php'?22:31);
   assert.equal(r.status,kind==='security'?'failed':'done');assert.equal(r.chain,'ok');scenarios.push({kind,...r});
  }
  // A genuine unavailable API is an error, never an automatic legacy switch.
  await context.route(base+'/api/v1/capabilities',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'unit_unavailable',message:'Release failure-path probe'}})}));
  await page.reload();await page.waitForFunction(()=>PP.control.state.mode==='error');
  assert.equal(await page.evaluate(()=>PP.control.state.mode),'error');
  assert.equal(errors.length,0,errors.join('\n'));assert.equal(external.length,0);
  console.log(JSON.stringify({passed:true,scenarios,widths:[1440,390],views:5,capabilities_503:'error; no fallback',javascript_errors:errors,external_requests:external,new_model_calls:0,screenshots:false},null,2));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
