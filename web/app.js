// Live panel: map (Leaflet) + controls + charts (Chart.js), fed by /ws/state.
const API = "";  // same origin: nginx proxies /api and /ws to sim-api
const SIGNAL_COLORS = { G: "#22c55e", g: "#16a34a", y: "#facc15", Y: "#facc15", r: "#ef4444", s: "#ef4444", u: "#f97316", o: "#94a3b8", O: "#94a3b8" };
const STRATEGY_COLORS = { fixed: "#94a3b8", maxpressure: "#a78bfa", rl: "#38bdf8" };
const MAX_POINTS = 600;

const map = L.map("map", { preferCanvas: true, zoomControl: true });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 20, maxNativeZoom: 19,
  attribution: "© colaboradores de OpenStreetMap",
}).addTo(map);
const renderer = L.canvas({ padding: 0.3 });
const vehicleLayer = L.layerGroup().addTo(map);
const signalLayer = L.layerGroup().addTo(map);
const vehicleMarkers = new Map();
const signalMarkers = [];  // {marker, tls, index}
let accidentSite = null, accidentMarker = null;

const ui = (id) => document.getElementById(id);
let current = { paused: false, speed: 5, strategy: "fixed", demand: "peak", accident_lane: null, run: 0 };

// ---------- charts ----------
function makeChart(canvas, unit) {
  return new Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false, parsing: false, normalized: true,
      plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
      scales: {
        x: { type: "linear", title: { display: true, text: "tiempo simulado (s)", color: "#9fb0d0" }, ticks: { color: "#9fb0d0" }, grid: { color: "#22324f" } },
        y: { beginAtZero: true, title: { display: true, text: unit, color: "#9fb0d0" }, ticks: { color: "#9fb0d0" }, grid: { color: "#22324f" } },
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
    const color = STRATEGY_COLORS[strategy] || "#e2e8f0";
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
async function loadNetwork() {
  const geo = await (await fetch(`${API}/api/network`)).json();
  const roads = L.geoJSON(geo, {
    filter: (f) => f.properties.kind === "road",
    style: (f) => ({
      color: f.properties.corridor ? "#1d4ed8" : "#334155",
      weight: f.properties.corridor ? 2 + f.properties.lanes : 1 + f.properties.lanes * 0.6,
      opacity: f.properties.corridor ? 0.55 : 0.4,
    }),
    onEachFeature: (f, layer) => f.properties.name && layer.bindTooltip(f.properties.name, { sticky: true }),
  }).addTo(map);
  const corridor = L.geoJSON(geo, { filter: (f) => f.properties.corridor });
  map.fitBounds((corridor.getLayers().length ? corridor : roads).getBounds(), { padding: [40, 40], maxZoom: 17 });
  for (const f of geo.features) {
    const [lon, lat] = f.geometry.coordinates;
    if (f.properties.kind === "signal") {
      const marker = L.circleMarker([lat, lon], { renderer, radius: 5, weight: 1.5, color: "#0f172a", fillOpacity: 1, fillColor: "#ef4444" })
        .bindTooltip(`Semáforo ${f.properties.streets.join(" / ")}`)
        .addTo(signalLayer);
      signalMarkers.push({ marker, tls: f.properties.tls, index: f.properties.index });
    } else if (f.properties.kind === "accident_site") {
      accidentSite = [lat, lon];
    }
  }
}

// ---------- state ----------
function render(s) {
  current = { ...current, ...s };
  ui("clock").textContent = `t = ${Math.round(s.t)} s · ${(s.t / 60).toFixed(1)} min`;

  const seen = new Set();
  for (const v of s.vehicles) {
    seen.add(v.id);
    let m = vehicleMarkers.get(v.id);
    const color = v.type === "moto" ? "#fb923c" : "#22d3ee";
    if (!m) {
      m = L.circleMarker([v.lat, v.lon], { renderer, radius: v.type === "moto" ? 3 : 4, weight: 0.8, color: "#0f172a", fillColor: color, fillOpacity: 0.95 });
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
    sm.marker.setStyle({ fillColor: SIGNAL_COLORS[ch] || "#ef4444" });
  }

  if (s.accident_lane && accidentSite && !accidentMarker) {
    accidentMarker = L.marker(accidentSite, { icon: L.divIcon({ className: "", html: '<div style="font-size:28px;line-height:28px">⚠️</div>', iconSize: [28, 28], iconAnchor: [14, 14] }) })
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

(async () => {
  await setupControls();
  await loadNetwork();
  connect();
})();
