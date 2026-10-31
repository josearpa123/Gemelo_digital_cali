// Live panel: map (Leaflet) + controls + charts (Chart.js), fed by /ws/state.
// The same messages carry the new trace events, handed to traces.js.
const API = "";  // same origin: sim-api serves the panel, /api and /ws on :8000
const SIGNAL_COLORS = { G: "#2bff88", g: "#1fcf6c", y: "#ffd60a", Y: "#ffd60a", r: "#ff3b5c", s: "#ff3b5c", u: "#ff9f1c", o: "#7fa3bd", O: "#7fa3bd" };
const STRATEGY_COLORS = { fixed: "#7fa3bd", maxpressure: "#b388ff", rl: "#00e5ff" };
const STRATEGY_NAMES = { fixed: "TIEMPO FIJO", maxpressure: "MAX-PRESSURE", rl: "AGENTES RL" };
const DEMAND_NAMES = { peak: "HORA PICO", valley: "HORA VALLE", peak_plus: "PICO +30 %" };
const MAX_POINTS = 600;

const ui = (id) => document.getElementById(id);

// ---------- boot sequence (decorative; skipped with reduced motion) ----------
(function boot() {
  const lines = ["enlazando con SUMO 1.28 (libsumo)", "cargando red OSM · Av. Roosevelt, Cali", "sincronizando agentes RL · 4 intersecciones", "abriendo canal de trazas", "sistema en línea"];
  const box = ui("boot-lines");
  lines.forEach((text, i) => setTimeout(() => { const d = document.createElement("div"); d.textContent = text; box.appendChild(d); }, 220 * i));
  setTimeout(() => { ui("boot").classList.add("done"); setTimeout(() => ui("boot").remove(), 600); }, 1400);
})();
setInterval(() => { ui("clock-real").textContent = new Date().toLocaleTimeString("es-CO", { hour12: false }); }, 500);

const map = L.map("map", { preferCanvas: true, zoomControl: true });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 20, maxNativeZoom: 19,
  attribution: "© colaboradores de OpenStreetMap",
}).addTo(map);
map.on("move", () => {
  const c = map.getCenter();
  ui("coords").textContent = `${Math.abs(c.lat).toFixed(4)}°${c.lat >= 0 ? "N" : "S"} ${Math.abs(c.lng).toFixed(4)}°${c.lng >= 0 ? "E" : "O"} · Z${map.getZoom()}`;
});
const renderer = L.canvas({ padding: 0.3 });
const vehicleLayer = L.layerGroup().addTo(map);
const signalLayer = L.layerGroup().addTo(map);
const hubLayer = L.layerGroup().addTo(map);
const vehicleMarkers = new Map();
const signalMarkers = [];  // {marker, tls, index}
const hubs = new Map();  // tls -> {marker, name}
let selectedTls = null;
let accidentSite = null, accidentMarker = null;

let current = { paused: false, speed: 5, strategy: "fixed", demand: "peak", accident_lane: null, run: 0 };

// ---------- charts ----------
Chart.defaults.font.family = "'Share Tech Mono', monospace";
function makeChart(canvas, unit) {
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false, parsing: false, normalized: true,
      plugins: { legend: { labels: { color: "#d8f3ff", boxWidth: 12 } } },
      scales: {
        x: { type: "linear", title: { display: true, text: "tiempo simulado (s)", color: "#7fa3bd" }, ticks: { color: "#7fa3bd" }, grid: { color: "rgba(0,229,255,0.08)" } },
        y: { beginAtZero: true, title: { display: true, text: unit, color: "#7fa3bd" }, ticks: { color: "#7fa3bd" }, grid: { color: "rgba(0,229,255,0.08)" } },
      },
      elements: { point: { radius: 0 }, line: { borderWidth: 2 } },
    },
  });
}
const waitChart = makeChart(ui("chart-wait"), "s");
const queueChart = makeChart(ui("chart-queue"), "vehículos");
const strategyLabels = {};

function seriesFor(chart, run, strategy) {
  const key = `${run}-${strategy}`;
  let ds = chart.data.datasets.find((d) => d.key === key);
  if (!ds) {
    const color = STRATEGY_COLORS[strategy] || "#d8f3ff";
    ds = { key, label: `#${run} ${strategyLabels[strategy] || strategy}`, data: [], borderColor: color, backgroundColor: color };
    chart.data.datasets.push(ds);
    if (chart.data.datasets.length > 6) chart.data.datasets.shift();
  }
  return ds;
}

function pushPoint(chart, run, strategy, t, y) {
  const ds = seriesFor(chart, run, strategy);
  const last = ds.data[ds.data.length - 1];
  if (last && t - last.x < 5) return;  // one point every 5 simulated seconds
  ds.data.push({ x: t, y });
  if (ds.data.length > MAX_POINTS) ds.data.shift();
  chart.update("none");
}

// ---------- network ----------
function styleHub(tls) {
  const h = hubs.get(tls);
  if (!h) return;
  const fallback = (current.fallback_tls || []).includes(tls);
  const color = fallback ? "#ffb300" : "#00e5ff";
  h.marker.setStyle({ color, radius: tls === selectedTls ? 16 : 11, weight: tls === selectedTls ? 3 : 2, dashArray: fallback ? "4 3" : null });
  h.marker.setTooltipContent(`${h.name}${fallback ? " · TIEMPO FIJO (fallback)" : ""} · clic: filtrar trazas`);
}

async function loadNetwork() {
  const geo = await (await fetch(`${API}/api/network`)).json();
  const roads = L.geoJSON(geo, {
    filter: (f) => f.properties.kind === "road",
    style: (f) => ({
      color: f.properties.corridor ? "#00e5ff" : "#3a6a8a",
      weight: f.properties.corridor ? 2 + f.properties.lanes : 1 + f.properties.lanes * 0.6,
      opacity: f.properties.corridor ? 0.55 : 0.45,
    }),
    onEachFeature: (f, layer) => f.properties.name && layer.bindTooltip(f.properties.name, { sticky: true }),
  }).addTo(map);
  const corridor = L.geoJSON(geo, { filter: (f) => f.properties.corridor });
  map.fitBounds((corridor.getLayers().length ? corridor : roads).getBounds(), { padding: [40, 40], maxZoom: 17 });
  const centers = new Map();
  const names = {};
  for (const f of geo.features) {
    const [lon, lat] = f.geometry.coordinates;
    if (f.properties.kind === "signal") {
      const marker = L.circleMarker([lat, lon], { renderer, radius: 4, weight: 1, color: "#02060d", fillOpacity: 1, fillColor: "#ff3b5c" })
        .bindTooltip(`Semáforo ${f.properties.name}`)
        .addTo(signalLayer);
      marker.on("click", () => Traces.selectTls(f.properties.tls, f.properties.name));
      signalMarkers.push({ marker, tls: f.properties.tls, index: f.properties.index });
      const c = centers.get(f.properties.tls) || { lat: 0, lon: 0, n: 0, name: f.properties.name };
      c.lat += lat; c.lon += lon; c.n += 1;
      centers.set(f.properties.tls, c);
      names[f.properties.tls] = f.properties.name;
    } else if (f.properties.kind === "accident_site") {
      accidentSite = [lat, lon];
    }
  }
  // one clickable ring per intersection: selecting it filters its RL decisions in "Trazas"
  for (const [tls, c] of centers) {
    const marker = L.circleMarker([c.lat / c.n, c.lon / c.n], { radius: 11, weight: 2, color: "#00e5ff", fill: true, fillOpacity: 0.04, className: "tls-hub" })
      .bindTooltip(c.name)
      .addTo(hubLayer);
    marker.on("click", () => Traces.selectTls(tls, c.name));
    hubs.set(tls, { marker, name: c.name });
    styleHub(tls);
  }
  return names;
}

// ---------- state ----------
function render(s) {
  current = { ...current, ...s };
  ui("clock").textContent = `${Math.round(s.t)} s · ${(s.t / 60).toFixed(1)} min`;
  Traces.ingest(s.traces);

  const seen = new Set();
  for (const v of s.vehicles) {
    seen.add(v.id);
    let m = vehicleMarkers.get(v.id);
    const color = v.type === "moto" ? "#ff9f1c" : "#22d3ee";
    if (!m) {
      m = L.circleMarker([v.lat, v.lon], { renderer, radius: v.type === "moto" ? 2.6 : 3.4, weight: 0.6, color: "#02060d", fillColor: color, fillOpacity: 0.95 });
      m.addTo(vehicleLayer);
      vehicleMarkers.set(v.id, m);
    } else {
      m.setLatLng([v.lat, v.lon]);
    }
  }
  for (const [id, m] of vehicleMarkers) {
    if (!seen.has(id)) { vehicleLayer.removeLayer(m); vehicleMarkers.delete(id); }
  }

  const states = Object.fromEntries(s.tls.map((t) => [t.id, t.state]));
  for (const sm of signalMarkers) {
    const ch = (states[sm.tls] || "")[sm.index] || "r";
    sm.marker.setStyle({ fillColor: SIGNAL_COLORS[ch] || "#ff3b5c" });
  }
  for (const tls of hubs.keys()) styleHub(tls);

  if (s.accident_lane && accidentSite && !accidentMarker) {
    accidentMarker = L.marker(accidentSite, { icon: L.divIcon({ className: "", html: '<div style="font-size:28px;line-height:28px;filter:drop-shadow(0 0 8px #ff3b5c)">⚠️</div>', iconSize: [28, 28], iconAnchor: [14, 14] }) })
      .bindTooltip("Accidente: carril cerrado").addTo(map);
  } else if (!s.accident_lane && accidentMarker) {
    map.removeLayer(accidentMarker); accidentMarker = null;
  }

  const m = s.metrics;
  ui("k-veh").textContent = m.vehicles;
  ui("k-queue").textContent = m.queue;
  ui("k-wait").textContent = `${m.mean_trip_wait.toFixed(1)} s`;
  ui("k-arr").textContent = m.arrived;
  pushPoint(waitChart, s.run, s.strategy, s.t, m.mean_wait_now);
  pushPoint(queueChart, s.run, s.strategy, s.t, m.queue);
  syncControls();
  ui("error").hidden = !s.error;
  if (s.error) ui("error").textContent = `Error de simulación: ${s.error}`;
}

function syncControls() {
  document.querySelectorAll("#strategies button").forEach((b) => b.classList.toggle("active", b.dataset.id === current.strategy));
  ui("pause").textContent = current.paused ? "▶ Reanudar" : "⏸ Pausar";
  ui("pause").classList.toggle("active", current.paused);
  ui("accident").classList.toggle("active", !!current.accident_lane);
  ui("accident").textContent = current.accident_lane ? "✓ Despejar accidente" : "⚠ Provocar accidente";
  ui("demand").textContent = current.demand === "peak" ? "🌙 Pasar a hora valle" : "🚗 Pasar a hora pico";
  ui("speed").value = String(current.speed);
  ui("chip-strategy").textContent = STRATEGY_NAMES[current.strategy] || current.strategy;
  ui("chip-demand").textContent = DEMAND_NAMES[current.demand] || current.demand;
  const armed = current.faults_armed || [];
  ui("chip-faults").hidden = !armed.length;
  ui("chip-faults").textContent = `FALLO ARMADO ×${armed.length}`;
}

async function control(action, value) {
  const res = await fetch(`${API}/api/control`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, value }),
  });
  if (!res.ok) { alert((await res.json()).detail || res.statusText); return; }
  current = { ...current, ...(await res.json()) };
  syncControls();
}

async function setupControls() {
  const info = await (await fetch(`${API}/api/strategies`)).json();
  for (const s of info.strategies) {
    strategyLabels[s.id] = s.label;
    const b = document.createElement("button");
    b.dataset.id = s.id;
    b.disabled = !s.available;
    b.innerHTML = `${s.label}${s.note ? `<small>${s.note}</small>` : ""}`;
    b.onclick = () => control("strategy", s.id);
    ui("strategies").appendChild(b);
  }
  for (const sp of info.speeds) {
    const o = document.createElement("option");
    o.value = sp; o.textContent = `${sp}×`;
    ui("speed").appendChild(o);
  }
  ui("speed").onchange = (e) => control("speed", Number(e.target.value));
  ui("pause").onclick = () => control("pause", !current.paused);
  ui("accident").onclick = () => control("accident", !current.accident_lane);
  ui("demand").onclick = () => control("demand", current.demand === "peak" ? "valley" : "peak");
  ui("restart").onclick = () => control("restart", current.strategy);
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/state`);
  ws.onopen = () => ui("conn").classList.add("on");
  ws.onmessage = (e) => render(JSON.parse(e.data));
  ws.onclose = () => { ui("conn").classList.remove("on"); setTimeout(connect, 1500); };
}

// page coordinates of an intersection ring (used by the e2e test to click it like a user)
window.hubScreenPoint = (i) => {
  const { marker } = [...hubs.values()][i];
  const p = map.latLngToContainerPoint(marker.getLatLng());
  const box = map.getContainer().getBoundingClientRect();
  return { x: box.left + p.x, y: box.top + p.y };
};

Traces.onTls((tls) => { selectedTls = tls; for (const t of hubs.keys()) styleHub(t); });

(async () => {
  await setupControls();
  const names = await loadNetwork();
  await Traces.init(names);
  connect();
})();
