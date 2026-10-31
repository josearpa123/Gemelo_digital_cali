// "Trazas" section + LLM assistant: live timeline fed by /ws/state (via app.js), indicators
// from /api/traces/summary, fault injection, panel-entered API key.
const Traces = (() => {
  const MAX_EVENTS = 3000;
  const MAX_ROWS = 250;
  const LABELS = { sim: "SIM", rl: "RL", event: "EVT", llm: "IA", training: "TRN" };
  const $ = (id) => document.getElementById(id);
  const events = new Map(); // seq -> event
  let filter = "all";
  let tls = null; // { id, name }
  let selected = null;
  let mode = "comando";
  let names = {};
  const listeners = { tls: [] };

  const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("es-CO", { hour12: false });
  const fmtSim = (t) => (t === null || t === undefined ? "—" : `T+${Math.round(t)}s`);
  const num = (x, d = 1) => (x === null || x === undefined ? "—" : Number(x).toFixed(d));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  async function api(path, opts = {}) {
    const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || res.statusText);
    return body;
  }

  // ---------- one-line description per event type ----------
  function describe(e) {
    const d = e.data || {};
    switch (e.type) {
      case "sim_segundo": {
        const v = d.vehiculos || {};
        return `${(v.carro || 0) + (v.moto || 0)} veh (${v.carro || 0} carros, ${v.moto || 0} motos, ${v.peaton || 0} peat.) · paso ${num(d.step_ms, 2)} ms · ${num(d.rtf, 0)}× tiempo real`;
      }
      case "escenario_inicio": return `inicio · ${d.zona} · escenario ${d.escenario} · ${d.estrategia} · semilla ${d.semilla_demanda}`;
      case "escenario_fin": return `fin · ${d.estrategia} · ${Math.round(d.duracion_s)} s · ${d.viajes} viajes · espera ${d.espera_media_viaje_s ?? "—"} s`;
      case "error_traci": return `ERROR TraCI: ${d.motivo}`;
      case "reconexion": return `reconexión en ${d.duracion_ms} ms · reanuda en T+${Math.round(d.reanuda_en_t)}s desde ${d.desde}`;
      case "decision": return `${d.interseccion}: fase ${d.fase_anterior}→${d.fase_elegida}${d.cambia ? "" : " (mantiene)"} · ${d.motivo} · r=${d.recompensa}`;
      case "fallback_control": return `${d.interseccion} → TIEMPO FIJO · ${d.motivo}`;
      case "control_recuperado": return `${d.interseccion}: vuelve el agente RL`;
      case "observacion_incompleta": return `${d.interseccion}: ${d.valores_perdidos}/${d.de} valores perdidos → ${d.respaldo}`;
      case "cambio_estrategia": return `estrategia ${d.de ?? "—"} → ${d.a}`;
      case "carga_modelo": return `modelo cargado ${d.modelo} (${d.carga_ms} ms)`;
      case "fallo_armado": return `fallo armado: ${d.label}`;
      case "accidente": return `accidente en ${d.calle} (${d.carril})${d.cerca_de ? ` cerca de ${d.cerca_de}` : ""}`;
      case "accidente_despejado": return `accidente despejado tras ${d.duracion_real_s} s`;
      case "cambio_demanda": return `demanda ${d.de} → ${d.a} (×${d.escala})`;
      case "pausa": return "simulación pausada";
      case "reanudacion": return "simulación reanudada";
      case "impacto": return `impacto ${d.evento} (+${d.ventana_s}s): espera ${d.antes.espera_media_s}→${d.despues.espera_media_s} s · cola ${d.antes.cola}→${d.despues.cola}`;
      case "respuesta_ok": return `respuesta ok · ${d.tokens_in}+${d.tokens_out} tokens · ${num(d.latency_s, 2)} s · US$ ${num(d.cost_paid_usd, 6)} eq.`;
      case "llamada_enviada": return `llamada a ${d.proveedor} · intento ${d.intento}${d.fallo_simulado ? ` · simulado: ${d.fallo_simulado}` : ""}`;
      case "consulta_creada": return `consulta (${d.modo}): ${d.texto || ""}`;
      case "reintento": return `reintento ${d.intento} en ${d.espera_s} s`;
      case "accion_validada": return `acción validada: ${d.accion?.accion}`;
      case "accion_ejecutada": return `acción ejecutada: ${d.resultado}`;
      case "accion_rechazada": return `acción rechazada: ${d.motivo}`;
      case "fallback_usado": return `fallback sin IA · ${d.motivo}`;
      case "episodio": return `episodio ${d.episodio}: recompensa ${d.recompensa_media} · espera ${d.espera_media_s ?? "—"} s · ${d.timesteps} timesteps`;
      default: {
        const text = d.error || d.motivo || d.texto || "";
        return `${e.type.replaceAll("_", " ")}${text ? ` · ${text}` : ""}`;
      }
    }
  }

  // ---------- timeline ----------
  function visible(e) {
    if (tls && e.tls_id !== tls.id) return false;
    if (filter === "all") return e.type !== "sim_segundo"; // per-second rows only under "Simulación"
    return e.component === filter;
  }

  function row(e) {
    const li = document.createElement("li");
    li.className = `${e.status}${selected === e.seq ? " sel" : ""}`;
    li.dataset.seq = e.seq;
    li.dataset.component = e.component;
    li.dataset.type = e.type;
    li.innerHTML = `<span class="n">#${e.seq}</span><span class="t">${fmtTime(e.ts)}</span><span class="t">${fmtSim(e.sim_t)}</span>`
      + `<span class="what"><span class="c ${e.component}">${LABELS[e.component]}</span>${esc(describe(e))}</span>`;
    li.title = describe(e);
    li.onclick = () => showDetail(e.seq);
    return li;
  }

  function render() {
    const list = $("trace-list");
    const rows = [...events.values()].filter(visible).sort((a, b) => b.seq - a.seq).slice(0, MAX_ROWS);
    list.replaceChildren(...rows.map(row));
  }

  function ingest(batch) {
    if (!batch || !batch.length) return;
    const list = $("trace-list");
    for (const e of batch) {
      if (events.has(e.seq)) continue;
      events.set(e.seq, e);
      if (visible(e)) {
        const li = row(e);
        li.classList.add("new");
        list.prepend(li);
      }
    }
    while (list.children.length > MAX_ROWS) list.lastChild.remove();
    if (events.size > MAX_EVENTS) {
      const drop = [...events.keys()].sort((a, b) => a - b).slice(0, events.size - MAX_EVENTS);
      drop.forEach((k) => events.delete(k));
    }
  }

  async function showDetail(seq) {
    const e = events.get(seq);
    if (!e) return;
    selected = seq;
    document.querySelectorAll("#trace-list li").forEach((li) => li.classList.toggle("sel", Number(li.dataset.seq) === seq));
    const box = $("trace-detail");
    box.hidden = false;
    const head = `<h3>#${e.seq} · ${esc(e.component)} · ${esc(e.type)} · ${esc(e.status)}</h3>`
      + `hora real ${new Date(e.ts * 1000).toLocaleString("es-CO", { hour12: false })} · simulado ${fmtSim(e.sim_t)}\n`
      + `trace_id ${esc(e.trace_id)}${e.tls_id ? `\nintersección ${esc(names[e.tls_id] || e.tls_id)}` : ""}\n\n`;
    box.innerHTML = head + esc(JSON.stringify(e.data, null, 2)) + `\n\n<button class="tiny" id="trace-full">Ver traza completa</button>`;
    $("trace-full").onclick = async () => {
      const t = await api(`/api/traces/${encodeURIComponent(e.trace_id)}`);
      box.innerHTML = head + t.events.map((x) => `#${x.seq} ${fmtTime(x.ts)} ${fmtSim(x.sim_t)} ${x.type} [${x.status}]\n  ${esc(describe(x))}`).join("\n");
    };
  }

  function setFilter(f) {
    filter = f;
    document.querySelectorAll("#trace-filters button").forEach((b) => b.classList.toggle("active", b.dataset.filter === f));
    updateExport();
    render();
  }

  function selectTls(id, name) {
    tls = id && (!tls || tls.id !== id) ? { id, name: name || names[id] || id } : null;
    const box = $("tls-filter");
    box.hidden = !tls;
    if (tls) box.querySelector("span").textContent = `INTERSECCIÓN: ${tls.name}`;
    if (tls && filter !== "all" && filter !== "rl") setFilter("rl");
    listeners.tls.forEach((fn) => fn(tls && tls.id));
    updateExport();
    render();
    if (tls && mode === "explicar" && !$("assistant-input").value) {
      $("assistant-input").value = `¿Por qué ${tls.name} cambió de fase?`;
    }
  }

  function updateExport() {
    const q = new URLSearchParams();
    if (filter !== "all") q.set("component", filter);
    if (tls) q.set("tls_id", tls.id);
    $("trace-export").href = `/api/traces/export.csv${q.toString() ? `?${q}` : ""}`;
  }

  // ---------- indicators ----------
  function setKpi(id, value, alert = false) {
    const el = $(id);
    el.textContent = value;
    el.parentElement.classList.toggle("alert", alert);
  }

  async function refreshSummary() {
    try {
      const s = await api("/api/traces/summary");
      setKpi("tk-rtf", s.sim.real_time_factor === null ? "—" : `${num(s.sim.real_time_factor, 1)}×`);
      setKpi("tk-step", num(s.sim.step_ms, 2));
      setKpi("tk-dpm", s.rl.decisions_per_min);
      setKpi("tk-inf", num(s.rl.inference_ms, 2));
      setKpi("tk-fb", s.rl.fallback_tls.length, s.rl.fallback_tls.length > 0);
      setKpi("tk-calls", s.llm.calls);
      setKpi("tk-tokens", s.llm.tokens.toLocaleString("es-CO"));
      setKpi("tk-cost", s.llm.cost_real_usd.toFixed(4));
      setKpi("tk-paid", s.llm.cost_paid_usd.toFixed(4));
      setKpi("tk-fail", s.failures, s.failures > 0);
    } catch (err) { /* the next poll retries */ }
  }

  // ---------- faults ----------
  async function setupFaults() {
    const info = await api("/api/faults");
    const sel = $("fault-select");
    sel.innerHTML = `<option value="" disabled selected>Simular en la próxima ocasión…</option>`
      + info.available.map((f) => `<option value="${f.id}">${esc(f.label)}</option>`).join("");
    $("fault-arm").onclick = async () => {
      if (!sel.value) return;
      const rlFault = sel.value === "rl_no_response" || sel.value === "detector_loss";
      try {
        const res = await api("/api/faults/arm", { method: "POST", body: JSON.stringify({ fault: sel.value, tls_id: rlFault && tls ? tls.id : null }) });
        const where = res.armed.tls_id ? ` en ${names[res.armed.tls_id] || res.armed.tls_id}` : "";
        msg("fault-msg", `ARMADO${where}: ${res.armed.label}${res.note ? ` · ${res.note}` : ""}`, "ok");
      } catch (err) { msg("fault-msg", err.message, "bad"); }
    };
  }

  function msg(id, text, kind = "") {
    const el = $(id);
    el.textContent = text;
    el.className = `msg ${kind}`;
  }

  // ---------- assistant and key ----------
  function showLlm(info) {
    $("llm-provider").textContent = `${info.provider} · ${info.model} · plan ${info.plan}`;
    const badge = $("llm-key");
    if (!info.key_required) { badge.textContent = "sin clave necesaria"; badge.className = "badge ok"; }
    else if (info.key_configured) { badge.textContent = `clave: ${info.key_source === "panel" ? "panel" : ".env"}`; badge.className = "badge ok"; }
    else { badge.textContent = "sin clave · modo reglas"; badge.className = "badge bad"; }
  }

  async function setupAssistant() {
    showLlm(await api("/api/llm/info"));
    $("key-open").onclick = () => { $("key-form").hidden = !$("key-form").hidden; $("key-input").focus(); };
    $("key-form").onsubmit = async (ev) => {
      ev.preventDefault();
      const key = $("key-input").value.trim();
      if (!key) return;
      try {
        showLlm(await api("/api/llm/key", { method: "POST", body: JSON.stringify({ api_key: key, persist: true }) }));
        $("key-input").value = "";
        msg("key-msg", "Clave guardada en el servidor. Usa «Probar conexión».", "ok");
      } catch (err) { msg("key-msg", err.message, "bad"); }
    };
    $("key-test").onclick = async () => {
      msg("key-msg", "Probando…");
      const res = await api("/api/llm/test", { method: "POST" }).catch((err) => ({ ok: false, error: err.message }));
      msg("key-msg", res.ok ? `Conexión OK con ${res.model}` : `Sin conexión: ${res.error}`, res.ok ? "ok" : "bad");
    };
    $("key-clear").onclick = async () => {
      showLlm(await api("/api/llm/key", { method: "DELETE" }));
      msg("key-msg", "Clave del panel borrada.", "ok");
    };
    const placeholders = {
      comando: "Ej.: provoca un accidente en la Roosevelt",
      explicar: "Ej.: ¿por qué la Cra 39 cambió a verde? (o clic en una intersección)",
      resumen: "Opcional: en qué enfocarse",
    };
    document.querySelectorAll("#assistant-modes button").forEach((b) => {
      b.onclick = () => {
        mode = b.dataset.mode;
        document.querySelectorAll("#assistant-modes button").forEach((x) => x.classList.toggle("active", x === b));
        $("assistant-input").placeholder = placeholders[mode];
      };
    });
    $("assistant-form").onsubmit = async (ev) => {
      ev.preventDefault();
      const out = $("assistant-answer");
      out.textContent = "procesando…";
      try {
        const res = await api("/api/assistant", { method: "POST", body: JSON.stringify({ modo: mode, texto: $("assistant-input").value }) });
        const source = res.source === "llm" ? "IA" : "reglas (sin IA)";
        out.innerHTML = `${esc(res.answer)}<span class="src">fuente: ${source} · traza ${res.trace_id}${res.executed ? " · acción ejecutada" : ""}</span>`;
      } catch (err) { out.textContent = `Error: ${err.message}`; }
    };
  }

  async function init(tlsNames) {
    names = tlsNames || {};
    document.querySelectorAll("#trace-filters button").forEach((b) => { b.onclick = () => setFilter(b.dataset.filter); });
    $("tls-clear").onclick = () => selectTls(null);
    const initial = await api("/api/traces?limit=800");
    ingest(initial.events.reverse());
    render();
    await Promise.all([setupFaults(), setupAssistant()]);
    refreshSummary();
    setInterval(refreshSummary, 2000);
  }

  return {
    init, ingest, selectTls,
    onTls: (fn) => listeners.tls.push(fn),
    setNames: (n) => { names = { ...names, ...n }; },
  };
})();
