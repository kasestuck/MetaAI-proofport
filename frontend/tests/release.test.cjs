const {test}=require('node:test');
const assert=require('node:assert/strict');
const {harness,until}=require('./harness.cjs');
const F=require('./contract-fixtures.cjs');
const {createHash}=require('node:crypto');
function events(h){
 const e={seq:1,ts:'2026-11-02T00:00:00Z',type:'test_result',module:null,detail:'unit',prev_hash:'0'.repeat(64)};
 return [{...e,entry_hash:createHash('sha256').update(e.prev_hash+h.PP.integrity.canonical(e)).digest('hex')}];
}

for(const language of ['python','php']) test('saved '+language+' real-run label never implies a new live request',async t=>{
  const h=harness(()=>{throw Error('No replay network');});t.after(h.cleanup);
  const r=F.report(events(h));r.settings.pipeline='live';
  r.verification={language,ai_migration:true,model_calls:1,historical:{format:'proofport_saved_live_projection_v1',new_api_calls:0,kind:language,source_report_sha256:'a'.repeat(64)}};
  r.state.hashes.unchanged=true;r.state.chain_intact=true;r.state.status='done';
  assert.equal(await h.PP.store.loadReplay({size:100,text:async()=>JSON.stringify(r)}),true);
  await until(()=>h.PP.store.state.run.chain?.status==='ok');
  const p=h.PP.labels.provenance(h.PP.store.state.run);
  assert.match(p.label,/Saved real Meta run/);assert.match(p.desc,/not a new live run/);assert.equal(h.calls.length,0);
});

test('saved rejected real proposal stays needs review with a failed run',async t=>{
  const h=harness(()=>{throw Error('No replay network');});t.after(h.cleanup);
  const r=F.report(events(h));r.state.status='failed';r.state.hashes.unchanged=true;r.state.chain_intact=true;
  r.verification={language:'python',ai_migration:false,model_calls:1,security_fix:{status:'needs_review'},
    historical:{format:'proofport_saved_live_projection_v1',kind:'security',new_api_calls:0,source_report_sha256:'b'.repeat(64)}};
  await h.PP.store.loadReplay({size:100,text:async()=>JSON.stringify(r)});
  await until(()=>h.PP.store.state.run.chain?.status==='ok');
  assert.match(h.PP.labels.provenance(h.PP.store.state.run).label,/rejected \/ needs review/);
  assert.equal(h.PP.store.state.run.state.status,'failed');assert.equal(h.calls.length,0);
});

test('historical label cannot turn a broken browser chain into verified scope',async t=>{
 const h=harness(()=>{});t.after(h.cleanup);const e=events(h);e[0].detail='tampered';
 const r=F.report(e);r.state.status='done';r.state.hashes.unchanged=true;r.state.chain_intact=true;
 r.verification={language:'php',ai_migration:true,model_calls:1,historical:{format:'proofport_saved_live_projection_v1',kind:'php',new_api_calls:0,source_report_sha256:'a'.repeat(64)}};
 await h.PP.store.loadReplay({size:100,text:async()=>JSON.stringify(r)});
 await until(()=>h.PP.store.state.run.chain?.status==='broken');
 assert.match(h.PP.labels.provenance(h.PP.store.state.run).label,/not verified/);
});
