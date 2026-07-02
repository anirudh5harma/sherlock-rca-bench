"use strict";

const API = ""; // same-origin (FastAPI serves this static bundle)
const AGENTS = ["metrics-agent", "deploy-agent", "logs-agent", "correlator"];

let scenarios = [];
let selected = null;
let currentReport = null;

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt != null) n.textContent = txt; return n; };
const pct = (x) => Math.round((x || 0) * 100);
const now = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

// ---- boot ----
init();
async function init() {
  await loadHealth();
  await loadScenarios();
  $("#btn-investigate").addEventListener("click", investigate);
  $("#btn-bench").addEventListener("click", runBench);
  $("#bench-close").addEventListener("click", closeBench);
  $("#scrim").addEventListener("click", closeBench);
}

async function loadHealth() {
  const badge = $("#llm-badge");
  try {
    const h = await (await fetch(`${API}/api/health`)).json();
    const mode = h.llm_mode || "unknown";
    badge.textContent = `llm: ${mode}`;
    badge.className = "badge " + (mode === "openai" ? "badge-openai" : "badge-mock");
  } catch { badge.textContent = "llm: offline"; badge.className = "badge badge-mock"; }
}

async function loadScenarios() {
  const list = $("#scenario-list");
  try {
    scenarios = await (await fetch(`${API}/api/scenarios`)).json();
  } catch { list.innerHTML = '<li class="skeleton">backend not up yet…</li>'; return; }
  list.innerHTML = "";
  scenarios.forEach((s) => {
    const li = el("li");
    li.dataset.id = s.id;
    li.append(el("div", "s-title", s.title));
    const meta = el("div", "s-meta");
    meta.append(sevBadge(s.severity), el("span", null, `${(s.incident?.signals?.length || 0)} signals`));
    li.append(meta);
    li.addEventListener("click", () => selectScenario(s.id));
    list.append(li);
  });
}

function sevBadge(sev) { const s = el("span", `sev ${sev}`, (sev || "sev?").toUpperCase()); return s; }

function selectScenario(id) {
  selected = scenarios.find((s) => s.id === id);
  if (!selected) return;
  document.querySelectorAll(".scenario-list li").forEach((li) => li.classList.toggle("active", li.dataset.id === id));
  $("#empty-state").classList.add("hidden");
  $("#investigation").classList.remove("hidden");
  $("#inc-title").textContent = selected.title;
  const sev = $("#inc-sev"); sev.textContent = (selected.severity || "sev?").toUpperCase(); sev.className = `sev ${selected.severity}`;
  resetStage();
}

function resetStage() {
  $("#rca-card").classList.add("hidden");
  $("#rca-grade").classList.add("hidden");
  $("#run-latency").textContent = "";
  const chips = $("#agents"); chips.innerHTML = "";
  AGENTS.forEach((a) => {
    const c = el("div", "agent-chip"); c.dataset.agent = a;
    c.append(el("span", "dot"), el("span", null, a));
    chips.append(c);
  });
  $("#timeline").innerHTML = "";
}

function setChip(agent, state) {
  const c = document.querySelector(`.agent-chip[data-agent="${agent}"]`);
  if (c) { c.classList.remove("running", "done", "error"); if (state) c.classList.add(state); }
}

function addTimeline(ev) {
  const row = el("div", `tl-row phase-${ev.phase}`);
  const a = el("div", `tl-agent ${ev.agent}`, ev.agent);
  row.append(a, el("div", "tl-msg", ev.message));
  const tl = $("#timeline"); tl.append(row); tl.scrollTop = tl.scrollHeight;
}

// ---- investigate (SSE) ----
function investigate() {
  if (!selected) return;
  resetStage();
  const btn = $("#btn-investigate"); btn.disabled = true; btn.textContent = "Investigating…";
  const started = performance.now();

  const es = new EventSource(`${API}/api/investigate/stream?scenario_id=${encodeURIComponent(selected.id)}`);
  es.onmessage = (msg) => {
    let ev; try { ev = JSON.parse(msg.data); } catch { return; }
    if (ev.phase === "start") setChip(ev.agent, "running");
    else if (ev.phase === "finding" || ev.phase === "thinking") setChip(ev.agent, "running");
    else if (ev.phase === "done") setChip(ev.agent, "done");
    else if (ev.phase === "error") setChip(ev.agent, "error");
    if (ev.message) addTimeline(ev);

    if (ev.phase === "done" && ev.data && ev.data.report) {
      currentReport = ev.data.report;
      renderReport(currentReport);
      $("#run-latency").textContent = `${Math.round(performance.now() - started)} ms wall · ${currentReport.latency_ms} ms agents`;
      es.close();
      btn.disabled = false; btn.textContent = "⚡ Re-investigate";
    }
  };
  es.onerror = () => {
    addTimeline({ agent: "system", phase: "error", message: "stream error — is the backend running?" });
    es.close(); btn.disabled = false; btn.textContent = "⚡ Investigate";
  };
}

function renderReport(r) {
  AGENTS.forEach((a) => setChip(a, "done"));
  $("#rca-time").textContent = now();
  $("#rca-summary").textContent = r.summary || "";
  $("#rca-blast").textContent = r.blast_radius || "—";

  const hyp = $("#rca-hypotheses"); hyp.innerHTML = "";
  (r.hypotheses || []).forEach((h, i) => {
    const box = el("div", "hyp");
    const top = el("div", "hyp-top");
    top.append(el("div", "hyp-cause", `${i + 1}. ${h.cause}`), el("div", "hyp-cat", h.category || "unknown"));
    box.append(top);
    const conf = el("div", "conf");
    const bar = el("div", "conf-bar"); const fill = el("div", "conf-fill"); fill.style.width = pct(h.confidence) + "%"; bar.append(fill);
    conf.append(el("span", "mini", "confidence"), bar, el("span", "conf-val", pct(h.confidence) + "%"));
    box.append(conf);
    if (h.evidence && h.evidence.length) {
      const ev = el("div", "evidence");
      h.evidence.forEach((e) => ev.append(el("span", "ev-chip", e)));
      box.append(ev);
    }
    hyp.append(box);
  });

  const next = $("#rca-next"); next.innerHTML = "";
  (r.next_steps || []).forEach((s) => next.append(el("li", null, s)));

  $("#rca-card").classList.remove("hidden");
  $("#rca-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---- benchmark ----
async function runBench() {
  openBench();
  const summary = $("#bench-summary"); const table = $("#bench-table");
  summary.innerHTML = '<span class="skeleton">running agent + judge over all scenarios…</span>';
  table.innerHTML = "";
  let res;
  try {
    res = await (await fetch(`${API}/api/bench/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
  } catch { summary.innerHTML = '<span class="skeleton">bench failed — backend not reachable.</span>'; return; }

  summary.innerHTML = "";
  summary.append(
    stat("Mean overall", pct(res.mean_overall) + "%", gradeClass(res.mean_overall)),
    stat("Hallucination", pct(res.hallucination_rate) + "%", res.hallucination_rate > 0.1 ? "g-bad" : "g-good"),
    stat("Mean latency", (res.mean_latency_ms || 0) + " ms", ""),
    stat("Model", res.model || "—", "")
  );

  table.innerHTML = "";
  const head = el("div", "bt-row head");
  ["Scenario", "Root", "Evid", "Next", "Overall"].forEach((h, i) => { const c = el("div", i === 0 ? "bt-name" : "bt-cell", h); head.append(c); });
  table.append(head);
  (res.scores || []).forEach((s) => {
    const row = el("div", "bt-row");
    const name = el("div", "bt-name", s.scenario_id);
    if (s.hallucination) name.append(el("span", "hyp-cat", "⚠ halluc"));
    row.append(name,
      cell(pct(s.root_cause_match) + "%"),
      cell(pct(s.evidence_recall) + "%"),
      cell(pct(s.next_step_usefulness) + "%"),
      cell(pct(s.overall) + "%", gradeClass(s.overall)));
    table.append(row);
  });
}

function cell(txt, cls) { const c = el("div", "bt-cell " + (cls || ""), txt); return c; }
function stat(lab, val, cls) {
  const s = el("div", "grade-stat");
  s.append(el("div", "g-val " + (cls || ""), val), el("div", "g-lab", lab));
  return s;
}
function gradeClass(x) { return x >= 0.75 ? "g-good" : x >= 0.5 ? "g-warn" : "g-bad"; }

function openBench() { $("#bench-drawer").classList.remove("hidden"); $("#scrim").classList.remove("hidden"); }
function closeBench() { $("#bench-drawer").classList.add("hidden"); $("#scrim").classList.add("hidden"); }
