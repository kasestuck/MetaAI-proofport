const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createHash}=require('node:crypto');
const {harness,flush,until}=require('./harness.cjs');
const F=require('./contract-fixtures.cjs');
function entries(h) {
  let prev='0'.repeat(64);
  return [1,2].map(seq=>{
    const e={seq,ts:'2026-11-02T00:00:00Z',type:'test_result',module:null,detail:'unit',prev_hash:prev};
    e.entry_hash=createHash('sha256').update(prev+h.PP.integrity.canonical(e)).digest('hex');
    prev=e.entry_hash;return e;
  });
}
for(const kind of ['duplicate','reordered']) test('saved evidence '+kind+' stays broken, never sorted/deduplicated green',async t=>{
  const h=harness(()=>{throw Error('Replay must make no API call');});t.after(h.cleanup);
  const e=entries(h);const supplied=kind==='duplicate'?[e[0],e[0],e[1]]:[e[1],e[0]];
  const report=F.report(supplied);
  assert.equal(await h.PP.store.loadReplay({name:'proofport-unit.json',size:100,text:async()=>JSON.stringify(report)}),true);
  await until(()=>h.PP.store.state.run.chain?.status==='broken');
  assert.equal(h.PP.store.state.run.events.length,supplied.length);
  assert.equal(h.calls.length,0);
});
test('malformed evidence is rejected without throwing/rendering null entries',async t=>{
  const h=harness(()=>{});t.after(h.cleanup);
  const report=F.report([null]);
  assert.equal(await h.PP.store.loadReplay({size:100,text:async()=>JSON.stringify(report)}),false);
  assert.equal((await h.PP.integrity.verifyChain([null])).status,'broken');
});
