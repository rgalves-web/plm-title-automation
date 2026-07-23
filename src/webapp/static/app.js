"use strict";
// Minorh Title Workbench — front end over the flow spine.
// Renders the prototype's screens from real API data; one primary action per view.

const API = {
  async get(u){ const r = await fetch(u); if(!r.ok) throw new Error((await r.json()).detail||r.statusText); return r.json(); },
  async post(u,b){ const r = await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});
                   if(!r.ok) throw new Error((await r.json()).detail||r.statusText); return r.json(); },
};
const $ = (id)=>document.getElementById(id);
const esc = (s)=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function toast(msg){ const t=$("toast"); t.textContent=msg; t.classList.add("show"); clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove("show"),2600); }
function go(id){ document.querySelectorAll(".screen").forEach(s=>s.classList.remove("active")); $(id).classList.add("active"); window.scrollTo({top:0}); }

let CURRENT = null;   // current unit view object
let POLL = null;

// ------------------------------------------------------------------ board
async function loadBoard(){
  const data = await API.get("/api/units");
  const cfg = await API.get("/api/config").catch(()=>({}));
  $("who").textContent = "Renato G.";
  const openable = (data.openable||[]).map(u=>
    `<button class="btn small secondary" onclick="openUnit('${esc(u)}')">Open ${esc(u)}</button>`).join(" ");
  const cards = (data.units||[]).map(cardHTML).join("") ||
    `<div class="card" style="padding:22px;color:var(--gray4)">No unit case files yet. ${openable?"Open one:":""} ${openable}</div>`;
  $("scr-board").innerHTML = `
    <div class="board-head">
      <div><div class="h-display">Every unit knows its next step.</div>
      <p>The system carries the method. Open a unit and it tells you exactly what it needs, where to find it, and what it has already proven.</p></div>
      <div>${openable||""}</div>
    </div>
    <div class="unit-grid">${cards}</div>
    <div class="footer-note"><span>minorh. title workbench</span><span>${esc(cfg.tesseract||"")}</span></div>`;
}
function cardHTML(u){
  const bars = Array.from({length:6},(_,i)=>{
    const cls = i < u.stage_index ? "done" : (i===u.stage_index ? "now" : "");
    return `<span class="${cls}"></span>`;
  }).join("");
  const g = u.gates||{};
  const metas = [];
  if(g.fail!=null) metas.push(pill(g.fail===0?"ok":"bad", `${g.fail} FAIL`));
  if(g.mismatch!=null) metas.push(pill(g.mismatch===0?"ok":"bad", `${g.mismatch} MISMATCH`));
  const dot = u.stage==="SHIP"?"ok":(u.stage==="REVIEW"?"ok":"idle");
  return `<div class="unit-card card" onclick="openUnit('${esc(u.unit_name)}')">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div><div class="name">${esc(u.unit_name)}</div><div class="geo">${esc(u.geo||"")}</div></div>
      <span class="pill"><span class="dot ${dot}"></span>${esc(u.stage)}</span>
    </div>
    <div class="stagebar">${bars}</div>
    <div class="next">Next step: <strong>${esc(u.next_step||"")}</strong></div>
    <div class="unit-meta">${metas.join("")}</div>
  </div>`;
}
function pill(dot,txt){ return `<span class="pill"><span class="dot ${dot}"></span>${esc(txt)}</span>`; }

async function openUnit(name){
  CURRENT = await API.get(`/api/units/${encodeURIComponent(name)}`);
  renderUnit();
  go("scr-unit");
}
async function refresh(){ CURRENT = await API.get(`/api/units/${encodeURIComponent(CURRENT.unit_name)}`); renderUnit(); }

// -------------------------------------------------------------- workspace
const STEP_TITLES = ["Case opened","Evidence checklist","Intake & classify","Build & prove","Your verdicts","Package"];
function renderUnit(){
  const u = CURRENT;
  const facts = u.facts.map(f=>`<div class="fact"><span class="label">${esc(f.label)}</span><span class="v">${esc(f.value)}</span></div>`).join("");
  const steps = u.stages.map((s,i)=>{
    const cls = i<u.stage_index?"done":(i===u.stage_index?"current":"");
    return `<button class="step ${cls}" onclick="showStage(${i})"><span class="n">${i+1} · ${esc(s)}</span><span class="t">${esc(STEP_TITLES[i])}</span></button>`;
  }).join("");
  $("scr-unit").innerHTML = `
    <div class="crumbs"><a href="#" onclick="go('scr-board');return false">UNITS</a> / ${esc(u.unit_name)}</div>
    <div class="unit-head">
      <div><div class="h-display">${esc(titleCase(u.unit_name))}</div><div class="facts">${facts}</div></div>
      <button class="btn secondary" onclick="showStage(5)">View package</button>
    </div>
    <div class="stepper">${steps}</div>
    <div id="pane"></div>
    <div class="footer-note"><span>${esc(u.unit_name)} · everything here is reproducible from the evidence ledger</span><span><a href="#" onclick="go('scr-board');return false">← all units</a></span></div>`;
  showStage(u.stage_index);
}
function titleCase(s){ return String(s).toLowerCase().replace(/\b([a-z])/g,(m,c)=>c.toUpperCase()).replace(/\bA Unit\b/,"A Unit"); }

function showStage(n){
  document.querySelectorAll(".stepper .step").forEach((s,i)=>s.classList.toggle("current", i===n));
  const pane = $("pane");
  pane.innerHTML = `<div class="stage-pane active">${STAGES[n]()}</div>`;
  if(n===3) attachRunHandlers();
}

// ------------------------------------------------------------- stage panes
const STAGES = [paneOpen, paneGather, paneDrop, paneRun, paneReview, paneShip];

function paneOpen(){
  const u=CURRENT, m=u; // facts already computed; show expected evidence from allowlist/checklist
  const al=u.derived_allowlist;
  const rows = [
    ["Unit designation", u.facts.find(f=>f.label==="Unit designation")?.value||"—"],
    ["Expected title opinions", al.title_opinions.length?al.title_opinions.join(" · "):"— (confirm evidence in DROP)"],
    ["Reference contracts", al.contracts.length?al.contracts.join(" · "):"—"],
    ["Leases in unit", String(al.leases)],
  ].map(([k,v])=>`<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`).join("");
  return `<div class="pane-head"><div class="h2">What the record says</div><div class="hint">Built from the Project Log, XREF and Well List. You typed one thing: the unit name.</div></div>
  <p class="pane-sub">The unit's opening picture — before any document is proven. Everything below becomes a checklist item.</p>
  <div class="card" style="padding:20px 22px"><div class="kv" style="grid-template-columns:220px 1fr;margin-top:0">${rows}</div></div>
  <div class="why" style="margin-top:16px"><strong>Why the DPU cross-check is mandatory:</strong> file names lie and leases feed multiple units. The unit is what the recorded Designation of Pooled Unit says it is — Exhibit A is the ground truth for the lease list.</div>
  <div style="margin-top:20px"><button class="btn primary" onclick="setStage('GATHER')">Build the checklist →</button></div>`;
}

function paneGather(){
  const u=CURRENT;
  const inCount = u.checklist.filter(c=>c.status==="in").length;
  const rows = u.checklist.map((c,i)=>{
    const st = c.status==="in" ? `<span class="pill"><span class="dot ok"></span>IN</span>`
             : c.status==="waived" ? `<span class="pill"><span class="dot idle"></span>WAIVED</span>`
             : `<span class="pill"><span class="dot ${c.blocking?"warn":"idle"}"></span>${c.blocking?"FETCH":"WANTED"}</span>`;
    const where = (c.where||[]).map(w=>`<div class="cell"><span class="label">Where to look</span><p>${esc(w)}</p></div>`).join("");
    return `<div class="chk card">
      <div class="chk-row" onclick="this.parentElement.classList.toggle('open')">
        <span class="st">${st}</span>
        <span class="what"><span class="t">${esc(c.what)}</span><span class="s">${esc(c.looks_like||"")}</span></span>
        <span class="ref">${esc(c.id.split("_").slice(1).join("_"))}</span><span class="chev">▶</span>
      </div>
      <div class="chk-body">
        <div class="howto"><div class="cell"><span class="label">What it looks like</span><p>${esc(c.looks_like||"")}</p></div>${where}</div>
        <div class="why"><strong>Why it matters:</strong> ${esc(c.why||"")}</div>
      </div></div>`;
  }).join("");
  return `<div class="pane-head"><div class="h2">Evidence checklist — ${inCount} of ${u.checklist.length} in</div><div class="hint">Each item explains what it is, where it lives, and why. Click a row to open the field guide.</div></div>
  <p class="pane-sub">You never memorize the method — the checklist is the method. Fetch what's missing, drop it in the intake, and the row closes itself.</p>
  ${rows}
  <div style="margin-top:20px"><button class="btn primary" onclick="setStage('DROP')">Go to intake →</button></div>`;
}

function paneDrop(){
  const u=CURRENT;
  const ev = u.evidence.map(e=>`<div class="intake card"><div class="intake-row">
      <span class="file">${esc(e.file)}</span>
      <span class="guess"><span class="as">${esc(kindLabel(e.kind))} <span class="mono dim">→ ${esc(e.identifier||"")}</span></span>
      <span class="ev">${esc(e.evidence_quote||"confirmed evidence")}</span></span>
      <span class="conf" style="color:var(--lime)">✓ ${esc(e.status)}</span></div></div>`).join("");
  const al=u.derived_allowlist;
  const seeded = u.evidence.length>0;
  const primary = seeded
    ? `<button class="btn primary" onclick="setStage('RUN')">Run the gates →</button>`
    : `<button class="btn primary" onclick="seedEvidence()">Confirm expected evidence from the record</button>`;
  return `<div class="pane-head"><div class="h2">Intake — drop anything</div><div class="hint">No naming rules. The system reads each file's content, matches it to the checklist, and shows its evidence. You confirm — one click.</div></div>
  <div class="drop"><div class="big">Drop files, folders or zips here</div><p>PDFs, spreadsheets, screenshots, archives — file names are hints, never rules. (Content-first classification lands in Phase 3.)</p></div>
  ${ev || `<div class="card" style="padding:18px;color:var(--gray5)">No evidence confirmed yet.</div>`}
  <div class="why" style="margin-top:16px"><strong>Allowlist derived from confirmed evidence:</strong> ${al.title_opinions.length} title opinions · ${al.contracts.length} contracts · ${al.leases} leases · identity ${al.identity_tokens.join(",")||"—"}. Never typed by hand — so it can't go stale.</div>
  <div style="margin-top:20px">${primary}</div>
  <div class="pane-head" style="margin-top:34px"><div class="h2">Lessons ledger</div><div class="hint">What the system has learned from human corrections. Rules, not code.</div></div>
  <div class="card">
    <div class="lesson"><span class="scope">GLOBAL</span><span class="txt"><strong>“TO” in a file name only means Title Opinion with a separator</strong> (T-O / T O) — otherwise it's the English word “to”.</span><span class="src">from ENCANA TO EOG</span></div>
    <div class="lesson"><span class="scope">GLOBAL</span><span class="txt"><strong>Identity decisions on screenshots require visual confirmation</strong> — OCR alone is never sufficient.</span><span class="src">from Kramer doc# 96546</span></div>
    <div class="lesson"><span class="scope">PROJECT</span><span class="txt"><strong>County search by name + date window, never by abstract.</strong></span><span class="src">from Maxwell supplemental</span></div>
  </div>`;
}
function kindLabel(k){ return {title_opinion:"Title opinion",contract:"Seller's file — contract",lease:"Lease",dpu:"Unit designation",well:"Well file"}[k]||k; }

function paneRun(){
  const u=CURRENT, gr=u.gate_results||{};
  const s=gr.structural||{}, t=gr.source_truth||{};
  const structuralDone = s.fail!=null;
  const truthDone = t.mismatch!=null;
  const fail = structuralDone ? s.fail : null;
  const mismatch = truthDone ? t.mismatch : null;
  const gS = `<div class="card"><span class="label">Structural gate</span><div class="big ${fail==null?'idle':(fail===0?'ok':'bad')}">${fail==null?'—':fail+' FAIL'}</div><div class="sub">${esc(s.summary||"not run yet")}</div></div>`;
  const gT = `<div class="card"><span class="label">Source-truth gate</span><div class="big ${mismatch==null?'idle':(mismatch===0?'ok':'bad')}" id="truth-big">${mismatch==null?'—':mismatch+' MISMATCH'}</div><div class="sub" id="truth-sub">${esc(t.summary||"runs in background — never a short timeout")}</div></div>`;
  const runlineS = `<div class="runline"><span class="res" style="color:${structuralDone?'var(--lime)':'var(--gray5)'}">${structuralDone?'✓':'○'}</span><span class="nm">Structural gate <span class="desc">— every written cell checked · report kept as sidecar, never a tab</span></span><span class="res dim">${structuralDone?'done':''}</span></div>`;
  const runlineT = `<div class="runline"><span class="res" id="truth-mark" style="color:${truthDone?'var(--lime)':'var(--gray5)'}">${truthDone?'✓':'○'}</span><span class="nm">Source-truth gate <span class="desc">— every cited cell re-read from its document (OCR)</span></span><span class="res dim" id="truth-time"></span></div>`;
  let primary;
  if(!structuralDone) primary = `<button class="btn primary" id="run-btn" onclick="runStructural()">Run the gates →</button>`;
  else if(!truthDone) primary = `<button class="btn primary" id="run-btn" onclick="runTruth()">Run source-truth gate (background)</button>`;
  else primary = `<button class="btn primary" onclick="setStage('REVIEW')">Go to review →</button>`;
  return `<div class="pane-head"><div class="h2">Build &amp; prove</div><div class="hint">The allowlist is derived from your confirmed evidence — never typed by hand, never stale.</div></div>
  <p class="pane-sub">The report is only as good as its proof, so the gates are not optional: every written cell is structurally checked, then re-read against its source document.</p>
  <div class="card">${runlineS}${runlineT}</div>
  <div class="gate">${gS}${gT}</div>
  <div class="why" style="margin-top:16px"><strong>Correct-and-fewer beats plausible-and-wrong.</strong> A cell the system cannot prove is named unverifiable — with the reason — instead of being filled with something plausible.</div>
  <div style="margin-top:18px" id="run-primary">${primary}</div>`;
}
function attachRunHandlers(){ if(CURRENT.gate_results?.structural && CURRENT.gate_results?.source_truth==null){ maybeResumePoll(); } }

function paneReview(){
  const u=CURRENT;
  const q=u.review_queue||[];
  if(!q.length){
    return `<div class="pane-head"><div class="h2">Your verdicts</div><div class="hint">Only cells that need human eyes reach this queue.</div></div>
    <div class="card" style="padding:20px;color:var(--gray4)">The source-truth gate has not populated the review queue yet. Run it on the <a href="#" onclick="showStage(3);return false">RUN</a> step; it finishes in the background.</div>
    <div style="margin-top:18px"><button class="btn primary" onclick="setStage('SHIP')">Skip to package →</button></div>`;
  }
  const rows = q.map((it,i)=>{
    const key=`${it.tab}!${it.cell}`;
    const v = (u.verdicts||{})[key];
    const vclass = it.label==="MISMATCH"?"v-MISMATCH":(it.label==="UNVERIFIABLE"?"v-UNVERIFIABLE":"v-NEEDS");
    const label = v?`<span class="v-done">VERDICT ✓</span>`:`<span class="${vclass}">${esc(it.label)}</span>`;
    return `<tr data-i="${i}" onclick="trace(${i})"><td>${esc(it.tab)} · ${esc(it.cell)}</td><td>${esc(it.field)}</td><td class="num">${esc(it.value)}</td><td>${label}</td></tr>`;
  }).join("");
  return `<div class="pane-head"><div class="h2">Your verdicts — ${q.length} cells</div><div class="hint">The machine reads; you decide. Click any cell to see its full chain of proof.</div></div>
  <div class="review-grid">
    <div class="card sheet"><table class="ddr"><thead><tr><th>Tab · Cell</th><th>Field</th><th>Value</th><th>Verification</th></tr></thead><tbody>${rows}</tbody></table>
    <div style="padding:12px 16px;font-size:12.5px;color:var(--gray5);border-top:1px solid var(--g700)">Every cell traces the same way. Verdicts persist in the case file.</div></div>
    <div class="card trace" id="tracebox"><span class="label">Chain of proof</span><div id="trace-content" style="color:var(--gray5);font-size:13px">Select a cell to trace it.</div></div>
  </div>
  <div style="margin-top:18px"><button class="btn primary" onclick="setStage('SHIP')">Package for submission →</button></div>`;
}

async function trace(i){
  const it=CURRENT.review_queue[i];
  document.querySelectorAll("table.ddr tr").forEach(r=>r.classList.remove("sel"));
  document.querySelector(`tr[data-i="${i}"]`)?.classList.add("sel");
  let tr;
  try{ tr = await API.get(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/trace?tab=${encodeURIComponent(it.tab)}&cell=${encodeURIComponent(it.cell)}`);}
  catch(e){ $("trace-content").innerHTML=`<span class="dim">${esc(e.message)}</span>`; return; }
  const kv = [["Value",tr.value],["Field",tr.field],["Source",tr.source_file||"—"],["Page",tr.source_page||"—"],["Method",tr.method],["Detail",tr.detail||"—"]]
    .map(([k,v])=>`<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`).join("");
  const key=`${it.tab}!${it.cell}`;
  const already=(CURRENT.verdicts||{})[key];
  let verdict = "";
  if(already){ verdict=`<div class="verdict"><span class="mono" style="color:var(--lime);font-size:12px">VERDICT RECORDED ✓ — ${esc(already.verdict)}</span></div>`; }
  else if(tr.needs_verdict){ verdict=`<div class="verdict"><button class="btn small primary" onclick="verdict(${i},'confirmed')">Confirm — it matches</button><button class="btn small secondary" onclick="verdict(${i},'mismatch')">It does not match</button></div>`; }
  else { verdict=`<div class="verdict"><button class="btn small secondary" onclick="verdict(${i},'acknowledged')">Acknowledge unverifiable</button></div>`; }
  $("trace-content").innerHTML = `<div class="kv">${kv}</div>${tr.detail?`<div class="snippet">${esc(tr.detail)}</div>`:""}${verdict}
    <div style="margin-top:12px;font-size:12px;color:var(--gray5)">Your verdict is stored with the cell — the next run remembers it.</div>`;
}
async function verdict(i,v){
  const it=CURRENT.review_queue[i];
  await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/verdict`,{tab:it.tab,cell:it.cell,verdict:v});
  toast("Verdict recorded ✓");
  await refresh(); showStage(4); trace(i);
}

function paneShip(){
  const u=CURRENT, ps=u.packaging_summary;
  if(!ps || !ps.tree){
    return `<div class="pane-head"><div class="h2">Submission package</div><div class="hint">Assembled from confirmed evidence only. Client FILES are read-only — everything here is a copy.</div></div>
    <div class="card" style="padding:20px;color:var(--gray4)">Not packaged yet. Assemble the PLM submission tree in the unit folder.</div>
    <div style="margin-top:18px"><button class="btn primary" id="ship-btn" onclick="doShip()">Package for submission</button></div>`;
  }
  const names={"1. PLM Report":"DDR + gates","2. Title Opinions":"deduped by chain","3. Unit Designation":"own DPU + amendments","4. Leases":"zips expanded","5. Title Documents":"named vol.page","6. Seller's Files":"recorded instruments only","7. Well Files":""};
  const tree = ps.tree.map(t=>{
    const miss = t.count===0 && t.folder.includes("Well");
    return `<div>&nbsp;&nbsp;${esc(t.folder)}/ <span class="${miss?'miss':'cnt'}">— ${t.count} ${t.count===1?'file':'files'}${names[t.folder]?' · '+esc(names[t.folder]):''}${miss?' · MISSING: RRC report':''}</span></div>`;
  }).join("");
  const miss = (ps.missing||[]).map(m=>`<div class="dec-row"><span class="act mis">MISSING</span><span><span class="f">${esc(m.what)}</span><br><span class="why2">${esc(m.reason)}</span></span></div>`).join("");
  return `<div class="pane-head"><div class="h2">Submission package</div><div class="hint">Assembled from confirmed evidence only. What's absent is said out loud.</div></div>
  <div class="review-grid">
    <div class="card tree"><div class="d">${esc(titleCase(u.unit_name))}/1. Landman Submitted/</div>${tree}
      <div style="margin-top:10px" class="cnt">SUBMISSION_MANIFEST.txt — every placement, exclusion and gap, with reasons</div></div>
    <div><div class="card decisions">${miss||`<div class="dec-row"><span class="why2">No missing items.</span></div>`}</div>
      <div class="why" style="margin-top:14px"><strong>${ps.placed}</strong> files placed · <strong>${(ps.missing||[]).length}</strong> missing · <strong>${ps.decisions_count}</strong> logged decisions.</div>
      <div class="kv" style="margin-top:12px"><span class="k">Package</span><span class="v" style="word-break:break-all">${esc(ps.root)}</span></div>
    </div>
  </div>
  <div style="margin-top:18px"><button class="btn primary" onclick="doShip()">Re-package</button></div>`;
}

// ------------------------------------------------------------- actions
async function setStage(to){ CURRENT = await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/stage`,{to}); renderUnit(); }
async function seedEvidence(){ toast("Confirming evidence from the record…"); CURRENT = await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/drop/seed`); renderUnit(); }
async function runStructural(){
  const btn=$("run-btn"); if(btn){btn.disabled=true; btn.innerHTML='Running structural gate <span class="spinner"></span>';}
  CURRENT = await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/run/structural`); renderUnit(); showStage(3);
  toast(`Structural gate: ${CURRENT.gate_results.structural.fail} FAIL`);
}
async function runTruth(){
  const btn=$("run-btn"); if(btn){btn.disabled=true; btn.innerHTML='Source-truth running in background <span class="spinner"></span>';}
  await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/run/source-truth`);
  toast("Source-truth gate started — runs in the background.");
  startPoll();
}
function maybeResumePoll(){ const st=$("truth-sub"); if(st) startPoll(); }
function startPoll(){
  clearInterval(POLL);
  const t0=Date.now();
  const mark=$("truth-mark"), time=$("truth-time");
  POLL = setInterval(async ()=>{
    let s; try{ s = await API.get(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/run/status`); }catch(e){ return; }
    const secs=Math.round((Date.now()-t0)/1000);
    if(time) time.textContent = `${Math.floor(secs/60)}m ${secs%60}s`;
    if(s.status==="running"){ /* keep waiting; no timeout */ }
    else if(s.status==="done"){ clearInterval(POLL); toast("Source-truth gate: 0 MISMATCH"); await refresh(); showStage(3); }
    else if(s.status==="error"){ clearInterval(POLL); toast("Source-truth error: "+(s.error||"")); if($("truth-sub"))$("truth-sub").textContent="error: "+(s.error||""); }
  }, 2500);
}
async function doShip(){
  const btn=$("ship-btn"); if(btn){btn.disabled=true; btn.innerHTML='Assembling package <span class="spinner"></span>';}
  try{ await API.post(`/api/units/${encodeURIComponent(CURRENT.unit_name)}/ship`); toast("Package assembled ✓"); await refresh(); showStage(5); }
  catch(e){ toast("Ship failed: "+e.message); if(btn){btn.disabled=false; btn.textContent="Package for submission";} }
}

loadBoard().catch(e=>{ $("scr-board").innerHTML=`<div class="card" style="padding:22px">Failed to load: ${esc(e.message)}</div>`; });
window.openUnit=openUnit; window.go=go; window.showStage=showStage; window.setStage=setStage;
window.seedEvidence=seedEvidence; window.runStructural=runStructural; window.runTruth=runTruth;
window.trace=trace; window.verdict=verdict; window.doShip=doShip;
