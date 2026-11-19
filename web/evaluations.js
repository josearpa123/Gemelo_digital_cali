// Completed evaluations only. Text nodes keep model/run names out of HTML parsing.
(() => {
  const byId = (id) => document.getElementById(id);
  const select = byId("evaluation-run");
  const status = byId("evaluation-status");
  const results = byId("evaluation-results");
  const download = byId("evaluation-csv");
  const number = (value, digits = 1) => Number.isFinite(value) ? value.toFixed(digits) : "—";
  let requestVersion = 0;
  const scenarioLabel = (value) => ({peak: "Pico", valley: "Valle", event: "Evento"}[value] || value);
  function strategyLabel(value) {
    if (value === "fixed") return "Fijo";
    if (value === "maxpressure") return "Max-pressure";
    const match = value.match(/^rl:.*_a([^_]+)_s([^_]+)_/);
    return match ? `RL α=${match[1]} · s${match[2]}` : value;
  }

  function table(headers, rows, rowTitles = []) {
    const wrapper = document.createElement("div");
    wrapper.className = "evaluation-scroll";
    const element = document.createElement("table");
    const head = element.createTHead().insertRow();
    for (const text of headers) {
      const cell = document.createElement("th");
      cell.scope = "col"; cell.textContent = text; head.appendChild(cell);
    }
    const body = element.createTBody();
    for (const [index, values] of rows.entries()) {
      const row = body.insertRow();
      for (const text of values) row.insertCell().textContent = text;
      if (rowTitles[index]) row.cells[0].title = rowTitles[index];
    }
    wrapper.appendChild(element); return wrapper;
  }

  async function loadReport() {
    const version = ++requestVersion;
    results.replaceChildren(); download.hidden = true;
    if (!select.value) return;
    status.textContent = "Cargando evaluación…";
    try {
      const query = new URLSearchParams({run: select.value});
      const response = await fetch(`/api/evaluations/report?${query}`);
      if (!response.ok) throw new Error("No se pudo leer el reporte");
      const report = await response.json();
      if (version !== requestVersion) return;
      const split = {validation: "Validación", test: "Prueba final", legacy: "Evaluación histórica"}[report.split] || report.split;
      status.textContent = `${split} · semillas ${report.seeds.join(", ")} · ${report.seconds} s por corrida. Valores: media ± desviación entre semillas.`;
      if (report.seconds < 3600) status.textContent += " Corrida corta: comprobación técnica, no resultado final.";
      if (report.seeds.length < 5) status.textContent += " Muestra parcial: menos de cinco semillas.";
      if (Object.values(report.compatibility || {}).includes("unverified")) status.textContent += " Incluye modelos antiguos cuya compatibilidad de red no está verificada.";
      results.appendChild(table(
        ["Escenario / estrategia", "Espera (s)", "P95 medio (s)", "Máxima media (s)", "Completados (media)", "Sin terminar", "Cola máx. media", "Jain", "Teletransportes"],
        report.summary.map((row) => [
          `${scenarioLabel(row.scenario)} / ${strategyLabel(row.strategy)}`,
          `${number(row.mean_wait_mean)} ± ${number(row.mean_wait_std)}`,
          number(row.wait_p95_mean), number(row.wait_max_mean),
          number(row.completed_mean), number(row.unfinished_mean),
          number(row.queue_max_mean), number(row.jain_wait_mean, 3), number(row.teleports_mean),
        ]), report.summary.map((row) => row.strategy)
      ));
      if (report.comparisons.length) {
        const title = document.createElement("p");
        title.textContent = "Reducción de espera frente a cada referencia (positivo = mejora). IC 95 % por bootstrap sobre semillas.";
        results.appendChild(title);
        results.appendChild(table(["Escenario / modelo", "Referencia", "Reducción", "IC 95 %", "Semillas"],
          report.comparisons.map((row) => [
            `${scenarioLabel(row.scenario)} / ${strategyLabel(row.strategy)}`, strategyLabel(row.baseline),
            row.wait_reduction === null ? "Sin referencia positiva" : `${number(row.wait_reduction * 100)} %`,
            row.ci95_low === null ? "—" : `[${number(row.ci95_low * 100)}, ${number(row.ci95_high * 100)}] %`,
            String(row.n),
          ]), report.comparisons.map((row) => row.strategy)));
      }
      download.href = `/api/evaluations/runs.csv?${query}`;
      download.hidden = false;
    } catch (error) {
      if (version === requestVersion) status.textContent = error.message;
    }
  }

  async function refresh() {
    const previous = select.value;
    try {
      const response = await fetch("/api/evaluations");
      if (!response.ok) throw new Error("No se pudieron consultar las evaluaciones");
      const payload = await response.json();
      select.replaceChildren();
      for (const report of payload.evaluations) {
        const option = document.createElement("option");
        option.value = report.id; option.textContent = `${report.split} · ${report.id}`;
        select.appendChild(option);
      }
      if ([...select.options].some((option) => option.value === previous)) select.value = previous;
      if (!select.value) {
        ++requestVersion; results.replaceChildren(); download.hidden = true;
        status.textContent = "Todavía no hay evaluaciones completas. Aparecerán al terminar la validación del modelo.";
        return;
      }
      await loadReport();
    } catch (error) { status.textContent = error.message; }
  }
  select.addEventListener("change", loadReport);
  byId("evaluation-refresh").addEventListener("click", refresh);
  refresh();
})();
