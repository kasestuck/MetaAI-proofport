const {test}=require("node:test");
const assert=require("node:assert/strict");
const {harness,response,until,deferred,defaultReply}=require("./harness.cjs");
const F=require("./contract-fixtures.cjs");
const metadata=()=>({instance_id:F.capabilities.instance_id,enabled:true,model:"muse-spark-1.3",model_status:"available",error:null,
  profiles:[{id:"python_mathutils",language:"python",file:"mathutils.py",source_version:"2.7",target_version:"3.12",readiness:{can_start:true}},
    {id:"php_legacy",language:"php",file:"legacy.php",source_version:"7.4",target_version:"8.3",readiness:{can_start:true}}]});
function setup(t,reply=()=>undefined){
  const h=harness(call=>reply(call)|| (call.url==="/api/v1/live-demo"?response(metadata()):defaultReply(call)));
  t.after(h.cleanup);h.load("js/views/shared.js");h.load("js/live-demo.js");
  const host=h.document.createElement("div");h.document.appendChild(host);
  const component=h.PP.liveDemo.mount(host);
  host.querySelectorAll("button").find(b=>b.textContent==="Live Meta AI").dispatch("click");
  return {h,host,component};
}
const start=host=>host.querySelectorAll("button").find(b=>b.textContent.includes("Start paid"));
const checkbox=host=>host.querySelector('input[type="checkbox"]');

test("live mode needs backend readiness and fresh explicit consent; never sends a key",async t=>{
  const {h,host,component}=setup(t,call=>{
    if(call.url.endsWith("/confirm"))return response({approval_id:"test-one-use-approval",instance_id:F.capabilities.instance_id});
    if(call.url==="/api/v1/live-demo/runs")return response({run_id:"run-one"},202);
  });
  await until(()=>host.textContent.includes("Local prerequisites ready"));
  assert.equal(start(host).disabled,true);checkbox(host).checked=true;checkbox(host).dispatch("change");
  assert.equal(start(host).disabled,false);await component.submit();
  const confirm=h.calls.find(c=>c.url.endsWith("/confirm"));assert.deepEqual(confirm.payload,{profile:"python_mathutils",consent:true});
  const posted=h.calls.filter(c=>c.url==="/api/v1/live-demo/runs");assert.equal(posted.length,1);
  assert.ok(posted[0].headers["Idempotency-Key"]);assert.equal(posted[0].payload.approval_id,"test-one-use-approval");
  assert.equal(JSON.stringify(h.calls).includes("MODEL_API_KEY"),false);
});

test("unknown paid submission outcome is blocked without automatic retry",async t=>{
  const {h,host,component}=setup(t,call=>{
    if(call.url.endsWith("/confirm"))return response({approval_id:"test-one-use-approval",instance_id:F.capabilities.instance_id});
    if(call.url==="/api/v1/live-demo/runs")throw new Error("simulated lost response");
  });
  await until(()=>host.textContent.includes("Local prerequisites ready"));
  checkbox(host).checked=true;checkbox(host).dispatch("change");await component.submit();await component.submit();
  assert.equal(h.calls.filter(c=>c.url==="/api/v1/live-demo/runs").length,1);
  assert.match(host.textContent,/Outcome may be unknown/);assert.equal(start(host).disabled,true);
});

test("a late consent response cannot submit an edited PHP selection",async t=>{
  const wait=deferred();const {h,host,component}=setup(t,call=>call.url.endsWith("/confirm")?wait.promise:undefined);
  await until(()=>host.textContent.includes("Local prerequisites ready"));
  checkbox(host).checked=true;checkbox(host).dispatch("change");const submitted=component.submit();
  await until(()=>h.calls.some(c=>c.url.endsWith("/confirm")));
  const select=host.querySelector("select");select.value="php_legacy";select.dispatch("change");
  wait.resolve(response({approval_id:"old-approval",instance_id:F.capabilities.instance_id}));await submitted;
  assert.equal(h.calls.filter(c=>c.url==="/api/v1/live-demo/runs").length,0);
});

test("Docker/missing-key readiness blocks paid button with the actual reason",async t=>{
  const {host}=setup(t,call=>{if(call.url==="/api/v1/live-demo"){
    const m=metadata();m.profiles[0].readiness={can_start:false,error:{message:"Docker unavailable"}};return response(m);
  }});
  await until(()=>host.textContent.includes("Docker unavailable"));checkbox(host).checked=true;checkbox(host).dispatch("change");
  assert.equal(start(host).disabled,true);
});

test("PHP live demo provenance and saved replay stay distinct",t=>{
  const {h}=setup(t);const report=F.report();report.verification={language:"php",live_demo:{security_scanned:false}};
  const p=h.PP.labels.provenance({origin:"replay",report,state:report.state});
  assert.match(p.label,/Saved report/);assert.match(p.label,/PHP Live Meta AI demo/);assert.match(p.desc,/no new generation/);
});
