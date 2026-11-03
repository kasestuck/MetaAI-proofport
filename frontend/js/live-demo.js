/* Fixed P13 scopes. No credential form, automatic paid retry or fabricated progress. */
(function (PP) {
  "use strict";
  const {h} = PP.util;
  function mount(host, options={}) {
    let metadata = null, busy = false, pending = null, revision = 0;
    const profile = h("select", {class:"input", onchange: () => { revision++; consent.checked = false; update(); }});
    const consent = h("input", {type:"checkbox", onchange: () => {revision++;update();}});
    const status = h("div", {role:"status", class:"muted"});
    const result = h("div", {role:"status", class:"stack"});
    const error = h("div", {role:"alert", class:"muted"});
    const form = h("div", {class:"stack"});
    const refresh = h("button", {class:"btn",type:"button",onclick: load}, "Refresh readiness");
    const check = h("button", {class:"btn",type:"button",onclick: async () => {
      busy=true; update();
      try {
        const reply=await PP.api.demoCheckModel();
        error.textContent=reply.error ? reply.error.message : "Catalog access confirmed. No generation request was made.";
        await load();
      } catch(e) { error.textContent=e.message; }
      finally {busy=false;update();}
    }}, "Check model access (catalog only)");
    const start = h("button", {class:"btn btn--primary",type:"button",onclick: submit}, "Start paid live demo — up to $0.05");
    const attach = h("button", {class:"btn",type:"button",onclick: () => {
      const id=metadata && (metadata.active_run_id||metadata.last_run_id);
      if(id) PP.store.attach(id,{apiMode:"v1",instanceId:metadata.instance_id});
    }}, "Attach active / latest live run");
    const replay=PP.views.shared.replayButton("Saved Replay");
    replay.addEventListener("click",()=>{form.hidden=true;if(options.offlineHost)options.offlineHost.hidden=true;consent.checked=false;update();});
    const modes = h("div",{class:"row",style:{flexWrap:"wrap"}},
      h("button",{class:"btn",type:"button",onclick:()=>{form.hidden=false;if(options.offlineHost)options.offlineHost.hidden=true;consent.checked=false;update();}},"Live Meta AI"),
      h("button",{class:"btn",type:"button",onclick:()=>{
        form.hidden=true;if(options.offlineHost)options.offlineHost.hidden=false;consent.checked=false;update();
        PP.control.edit({operation:"migration",execution_mode:"offline_fixtures"});
      }},"Offline Fixtures"), replay);
    form.replaceChildren(profile,h("p",{class:"muted"},"Only Python mathutils (31 cases / 3 tests) or PHP legacy.php (22 cases / 9 tests). Originals stay unchanged; no live security fix or arbitrary project migration."),
      status,h("div",{class:"row",style:{flexWrap:"wrap"}},refresh,check,attach),
      h("label",{class:"field"},h("span",{},consent," I authorize this run: at most 2 calls, $0.05 estimated, 9216 input / 3072 output tokens per call, 30-second timeout. No automatic retry or fixtures.")),start,error,result);
    host.replaceChildren(h("div",{class:"card stack"},h("h2",{},"Real Meta AI demo"),modes,form));
    form.hidden=true; // Existing offline Run control remains the default.
    function update() {
      const selected=metadata && metadata.profiles.find(p=>p.id===profile.value);
      start.disabled=busy || !!pending || !metadata || metadata.enabled!==true || !selected?.readiness?.can_start || !consent.checked;
      check.disabled=busy; refresh.disabled=busy;
      attach.hidden=!metadata || !(metadata.active_run_id||metadata.last_run_id);
      status.textContent=metadata ? "Model: "+metadata.model+" — "+metadata.model_status+". "+(metadata.error ? metadata.error.message : selected?.readiness?.error?.message || "Local prerequisites ready; Docker/source checks repeat at confirmation and creation.") : "Readiness not loaded.";
    }
    async function load() {
      const old=metadata && metadata.instance_id;
      try {
        const next=await PP.api.demoMetadata();
        if(!next || typeof next.instance_id!=="string" || !Array.isArray(next.profiles) || typeof next.enabled!=="boolean") throw new Error("Invalid live demo metadata; no paid action allowed.");
        metadata=next;
        const selected=profile.value;
        profile.replaceChildren(...next.profiles.map(p=>h("option",{value:p.id},p.language+": "+p.file+" "+p.source_version+" → "+p.target_version)));
        profile.value=next.profiles.some(p=>p.id===selected)?selected:next.profiles[0]?.id||"";
        if(old && old!==next.instance_id){revision++;consent.checked=false;error.textContent="Backend instance changed; no old paid request was repeated.";}
      } catch(e){metadata=null;error.textContent=e.message;}
      update();
    }
    async function submit() {
      if(form.hidden || start.disabled || busy || pending) return;
      if(!window.confirm("Authorize one live Meta demo, maximum 2 model calls and $0.05 estimated? Verification may reject it; timeout billing can be unknown.")) return;
      const chosen=profile.value, version=revision, instance=metadata.instance_id;
      busy=true;error.textContent="";update();
      try {
        const approval=await PP.api.demoConfirm(chosen);
        if(version!==revision || !consent.checked || chosen!==profile.value || approval.instance_id!==instance) throw new Error("Form or instance changed; paid run was not submitted.");
        const key=window.crypto.randomUUID();
        pending={body:{profile:chosen,approval_id:approval.approval_id},key};
        const run=await PP.api.demoStart(pending.body,key);
        if(!run || typeof run.run_id!=="string") throw new Error("Uncertain submission response. Do not start another paid run.");
        PP.store.attach(run.run_id,{source:chosen,maxIterations:2,apiMode:"v1",instanceId:instance,language:chosen==="php_legacy"?"php":"python"});
        pending=null;consent.checked=false;
      } catch(e) {
        if(e.status>=400 && e.status<500) pending=null;
        error.textContent=e.message+(pending ? " Outcome may be unknown. No automatic retry; refresh readiness and attach the active run before deciding anything else." : "");
      } finally {busy=false;update();}
    }
    function render(state) {
      const run=state.run, details=run && run.control, demo=details && details.result && details.result.live_demo;
      if(!demo) {result.replaceChildren();return;}
      const metrics=details.state.metrics;
      const tests=details.result.target_tests;
      result.replaceChildren(h("div",{},"Model status: "+demo.model_status+" · Phase: "+details.state.phase+" · Backend: "+details.lifecycle),
        h("div",{},"Baseline cases recorded: "+(demo.baseline_golden_cases??"not yet recorded")+" · Target golden: "+(demo.golden_total>0?demo.golden_matched+" / "+demo.golden_total:"not yet verified")+" · Existing tests: "+(tests && tests.tests_run>0?tests.outcomes.filter(t=>t.status==="passed").length+" / "+tests.tests_run:demo.tests_total>0?demo.tests_passed+" / "+demo.tests_total:"not yet verified")),
        h("div",{},"Reported tokens: "+metrics.tokens_in+" in / "+metrics.tokens_out+" out · Estimated cost: "+(demo.billing_unknown?"unknown after provider/transport failure":demo.model_status==="requesting"?"awaiting provider usage":"$"+metrics.cost_usd.toFixed(8))),
        h("div",{},"Backend finalized: "+details.finalized+" · Report: "+run.reportStatus+" · Browser evidence: "+(run.chain?.status||"check Evidence tab")),
        h("p",{class:"muted"},"No security audit/remediation in this scoped live run. Report availability, backend completion and independent evidence verification are separate."));
    }
    PP.store.subscribe(render);load();
    return {load,submit,render};
  }
  PP.liveDemo={mount};
})(window.PP);
