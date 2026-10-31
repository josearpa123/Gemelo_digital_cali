"""Live simulation runner used by sim-api: one libsumo simulation, swappable strategies,
events (accident, demand level), traces and a JSON-friendly snapshot per step.

All methods must be called from the same thread (libsumo is not thread-safe)."""

import time
from collections import Counter, deque
from pathlib import Path

import libsumo
import sumolib

from sim.controllers import FixedTimeController, MaxPressureController
from sim.controllers.base import Controller
from sim.controllers.rl_policy import RLController, find_model
from sim.intersections import load_zone, tls_names
from sim.tracing import NullTracer, new_trace_id

DEMAND_LEVELS = {"valley": 0.45, "peak": 1.0, "peak_plus": 1.3}
CORRIDOR = "Calle 6"
SCENARIO_NAMES = {"valley": "valle", "peak": "pico", "event": "evento"}
VEHICLE_KINDS = {"car": "carro", "moto": "moto"}
IMPACT_WINDOW = 120  # simulated seconds between an event and its measured impact
CHECKPOINT_EVERY = 300  # simulated seconds between saved states (to resume after a crash)
RTF_WINDOW = 5.0  # wall seconds used for the real-time factor


class SimRunner:
    def __init__(
        self,
        net_file: Path,
        route_file: Path,
        seed: int = 0,
        sumo_args: list[str] | None = None,
        tracer=None,
        faults=None,
        state_dir: Path | None = None,
    ):
        self.net_file = Path(net_file)
        self.sumo_args = list(sumo_args or [])
        self.route_file = Path(route_file)
        self.seed = seed
        self.tracer = tracer or NullTracer()
        self.faults = faults
        self.state_dir = Path(state_dir) if state_dir else None
        self.net = sumolib.net.readNet(str(self.net_file), withPedestrianConnections=True)
        self.zone_name = self.net_file.parent.name
        self.zone = load_zone(self.zone_name)
        self.names = tls_names(self.zone)
        self.edge_names = {e.getID(): e.getName() for e in self.net.getEdges() if e.getName()}
        self.strategies = self._available_strategies()
        self.strategy = "fixed"
        self.controller: Controller = self.strategies["fixed"]()
        self.run_id = 0
        self.demand = "peak"
        self.accident_lane: str | None = None
        self._accident_allowed: list[str] = []
        self.running = False

    # ---- strategies -------------------------------------------------------------------
    def _available_strategies(self) -> dict:
        strategies = {"fixed": FixedTimeController, "maxpressure": MaxPressureController}
        model = find_model()
        if model is not None:
            strategies["rl"] = lambda: RLController(
                str(self.net_file),
                model,
                tracer=self.tracer,
                faults=self.faults,
                names=self.names,
                edge_names=self.edge_names,
                wait_cache=lambda: self.trip_wait,
            )
        self.model_path = model
        return strategies

    def strategy_list(self) -> list[dict]:
        labels = {"fixed": "Tiempo fijo", "maxpressure": "Max-pressure", "rl": "Agentes RL (PPO)"}
        out = []
        for key in ("fixed", "maxpressure", "rl"):
            item = {"id": key, "label": labels[key], "available": key in self.strategies}
            if key == "rl":
                item["note"] = self.model_path.parent.name if self.model_path else "sin modelo"
            out.append(item)
        return out

    # ---- lifecycle --------------------------------------------------------------------
    def _sumo_cmd(self) -> list[str]:
        return [
            "sumo",
            "-n",
            str(self.net_file),
            "-r",
            str(self.route_file),
            "--seed",
            str(self.seed),
            "--time-to-teleport",
            "300",
            "--no-step-log",
            "--no-warnings",
            "--waiting-time-memory",
            "3600",
            *self.sumo_args,
        ]

    def scenario_info(self) -> dict:
        """Zone, scenario and seed from the route file name (<scenario>_s<seed>.rou.xml)."""
        stem = self.route_file.name.split(".")[0]
        scenario, _, seed = stem.rpartition("_s")
        return {
            "zona": self.zone_name,
            "corredor": self.zone["corridor"],
            "escenario": SCENARIO_NAMES.get(scenario, scenario or stem),
            "semilla_demanda": int(seed) if seed.isdigit() else None,
            "semilla_sumo": self.seed,
            "rutas": self.route_file.name,
        }

    def start(self, strategy: str | None = None) -> None:
        if self.running:
            self._scenario_end()
            libsumo.close()
        strategy = strategy or self.strategy
        libsumo.start(self._sumo_cmd())
        self.running = True
        self.run_id += 1
        self.programs = {
            t: (libsumo.trafficlight.getProgram(t), libsumo.trafficlight.getAllProgramLogics(t))
            for t in libsumo.trafficlight.getIDList()
        }
        self.tls_lanes = {
            t: sorted(set(libsumo.trafficlight.getControlledLanes(t)))
            for t in libsumo.trafficlight.getIDList()
        }
        self.accident_lane = None
        self._accident_until: float | None = None
        self._accident_trace: str | None = None
        self._accident_start = 0.0
        self.demand = "peak"
        self.trip_wait: dict[str, float] = {}
        self.depart_time: dict[str, float] = {}
        self.finished_wait: deque[float] = deque(maxlen=2000)
        self.finished_travel: deque[float] = deque(maxlen=2000)
        self.arrived = 0
        self.teleports = 0
        self.vtype: dict[str, str] = {}
        self.vcount: Counter = Counter()
        self.pending_impacts: list[dict] = []
        self._second = -1
        self._second_ms: list[float] = []
        self._rtf_points: deque[tuple[float, float]] = deque()
        self._last_checkpoint: Path | None = None
        self.strategy = None
        self.tracer.emit(
            "sim",
            "escenario_inicio",
            data=self.scenario_info() | {"estrategia": strategy, "corrida": self.run_id},
            sim_t=0.0,
        )
        self.set_strategy(strategy)

    def _scenario_end(self) -> None:
        mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
        self.tracer.emit(
            "sim",
            "escenario_fin",
            data=self.scenario_info()
            | {
                "estrategia": self.strategy,
                "corrida": self.run_id,
                "duracion_s": libsumo.simulation.getTime(),
                "viajes": self.arrived,
                "espera_media_viaje_s": mean(self.finished_wait),
                "teletransportes": self.teleports,
            },
            sim_t=libsumo.simulation.getTime(),
        )

    def close(self) -> None:
        if self.running:
            self._scenario_end()
            libsumo.close()
            self.running = False

    def set_strategy(self, strategy: str) -> None:
        if strategy not in self.strategies:
            raise ValueError(f"strategy not available: {strategy}")
        previous = self.strategy
        if self.strategy is not None:
            self.controller.deactivate(libsumo, self.programs)
        self.controller = self.strategies[strategy]()
        self.controller.activate(libsumo, self.programs)
        self.strategy = strategy
        self.tracer.emit(
            "rl",
            "cambio_estrategia",
            data={"de": previous, "a": strategy},
            sim_t=libsumo.simulation.getTime(),
        )

    @property
    def fallback_tls(self) -> list[str]:
        return list(getattr(self.controller, "fallback_tls", []))

    # ---- events -----------------------------------------------------------------------
    def accident_candidate(self) -> str:
        """A lane of the Roosevelt approaching a signalised junction (longest, multi-lane edge)."""
        controlled = {lane for lanes in self.tls_lanes.values() for lane in lanes}
        edges = [
            e
            for e in self.net.getEdges()
            if e.getName() == CORRIDOR
            and e.getLaneNumber() >= 2
            and any(lane.getID() in controlled for lane in e.getLanes())
        ]
        edge = max(edges, key=lambda e: e.getLength())
        lanes = [lane for lane in edge.getLanes() if lane.allows("passenger")]
        # leftmost lane whose closure keeps every incoming and outgoing movement possible;
        # otherwise vehicles routed through the closed lane stop SUMO with "no valid route"
        for lane in reversed(lanes):
            if self._closable(edge, lane):
                return lane.getID()
        return lanes[-1].getID()

    @staticmethod
    def _closable(edge, lane) -> bool:
        for other in edge.getIncoming():
            targets = {c.getToLane() for c in other.getConnections(edge)}
            if targets and targets <= {lane}:
                return False
        for other in edge.getOutgoing():
            sources = {c.getFromLane() for c in edge.getConnections(other)}
            if sources and sources <= {lane}:
                return False
        return True

    def set_accident(
        self, active: bool, lane: str | None = None, duration: float | None = None
    ) -> str | None:
        """Close (or reopen) a lane. Returns the trace id of the event."""
        now = libsumo.simulation.getTime()
        if active and self.accident_lane is None:
            lane = lane or self.accident_candidate()
            self._accident_allowed = list(libsumo.lane.getAllowed(lane))
            libsumo.lane.setAllowed(lane, ["authority"])
            libsumo.lane.setMaxSpeed(lane, 1.0)
            self.accident_lane = lane
            self._accident_start = now
            self._accident_until = now + duration if duration else None
            edge = lane.rsplit("_", 1)[0]
            tls = next((t for t, lanes in self.tls_lanes.items() if lane in lanes), None)
            self._accident_trace = self._event(
                "accidente",
                {
                    "calle": self.edge_names.get(edge, edge),
                    "carril": lane,
                    "cerca_de": self.names.get(tls, tls) if tls else None,
                    "duracion_s": duration,
                },
                tls_id=tls,
            )
            return self._accident_trace
        if not active and self.accident_lane is not None:
            lane = self.accident_lane
            libsumo.lane.setAllowed(lane, self._accident_allowed)
            libsumo.lane.setMaxSpeed(lane, self.net.getLane(lane).getSpeed())
            self.accident_lane = None
            self._accident_until = None
            return self._event(
                "accidente_despejado",
                {"carril": lane, "duracion_real_s": round(now - self._accident_start, 1)},
                trace_id=self._accident_trace,
                impact=False,
            )
        return None

    def set_demand(self, level: str) -> str:
        if level not in DEMAND_LEVELS:
            raise ValueError(f"demand must be one of {list(DEMAND_LEVELS)}")
        libsumo.simulation.setScale(DEMAND_LEVELS[level])
        previous, self.demand = self.demand, level
        return self._event(
            "cambio_demanda", {"de": previous, "a": level, "escala": DEMAND_LEVELS[level]}
        )

    def mark(self, kind: str) -> str:
        """Trace an event decided outside the simulation thread's state (pause, resume)."""
        return self._event(kind, {})

    def quick_metrics(self) -> dict:
        waits = [libsumo.vehicle.getWaitingTime(v) for v in libsumo.vehicle.getIDList()]
        queue = sum(
            libsumo.lane.getLastStepHaltingNumber(lane)
            for lanes in self.tls_lanes.values()
            for lane in lanes
        )
        return {
            "espera_media_s": round(sum(waits) / len(waits), 2) if waits else 0.0,
            "cola": queue,
            "vehiculos": len(waits),
        }

    def _event(
        self,
        kind: str,
        data: dict,
        tls_id: str | None = None,
        trace_id: str | None = None,
        impact: bool = True,
    ) -> str:
        now = libsumo.simulation.getTime()
        trace_id = trace_id or new_trace_id()
        before = self.quick_metrics()
        self.tracer.emit(
            "event",
            kind,
            data=data | {"antes": before},
            sim_t=now,
            tls_id=tls_id,
            trace_id=trace_id,
        )
        if impact:
            self.pending_impacts.append(
                {"trace_id": trace_id, "evento": kind, "at": now + IMPACT_WINDOW, "antes": before}
            )
        return trace_id

    def _check_impacts(self, now: float) -> None:
        due = [p for p in self.pending_impacts if now >= p["at"]]
        if not due:
            return
        self.pending_impacts = [p for p in self.pending_impacts if now < p["at"]]
        after = self.quick_metrics()
        for p in due:
            before = p["antes"]
            self.tracer.emit(
                "event",
                "impacto",
                data={
                    "evento": p["evento"],
                    "ventana_s": IMPACT_WINDOW,
                    "antes": before,
                    "despues": after,
                    "delta_espera_s": round(after["espera_media_s"] - before["espera_media_s"], 2),
                    "delta_cola": after["cola"] - before["cola"],
                },
                sim_t=now,
                trace_id=p["trace_id"],
            )

    # ---- stepping ---------------------------------------------------------------------
    def step(self) -> None:
        started = time.perf_counter()
        try:
            if self.faults and self.faults.take("traci_disconnect"):
                raise libsumo.FatalTraCIError("conexión con SUMO perdida (fallo simulado)")
            self._advance()
        except (libsumo.FatalTraCIError, libsumo.TraCIException) as exc:
            self._reconnect(str(exc))
            return
        now = libsumo.simulation.getTime()
        self._trace_second(now, (time.perf_counter() - started) * 1000)
        if self._accident_until is not None and now >= self._accident_until:
            self.set_accident(False)
        if self.pending_impacts:
            self._check_impacts(now)
        if self.state_dir and now % CHECKPOINT_EVERY == 0:
            self._checkpoint()

    def _advance(self) -> None:
        self.controller.step(libsumo)
        libsumo.simulationStep()
        self.controller.after_step()
        now = libsumo.simulation.getTime()
        self.teleports += libsumo.simulation.getStartingTeleportNumber()
        for vid in libsumo.simulation.getDepartedIDList():
            self.depart_time[vid] = now
            kind = VEHICLE_KINDS.get(libsumo.vehicle.getTypeID(vid), "otro")
            self.vtype[vid] = kind
            self.vcount[kind] += 1
        for vid in libsumo.vehicle.getIDList():
            self.trip_wait[vid] = libsumo.vehicle.getAccumulatedWaitingTime(vid)
        for vid in libsumo.simulation.getArrivedIDList():
            self.arrived += 1
            self.finished_wait.append(self.trip_wait.pop(vid, 0.0))
            if vid in self.depart_time:
                self.finished_travel.append(now - self.depart_time.pop(vid))
            kind = self.vtype.pop(vid, None)
            if kind:
                self.vcount[kind] -= 1

    def _trace_second(self, now: float, step_ms: float) -> None:
        """One aggregated `sim_segundo` event per simulated second (not per step)."""
        if not self.tracer.enabled:
            return
        self._second_ms.append(step_ms)
        second = int(now)
        if second == self._second:
            return
        self._second = second
        wall = time.perf_counter()
        points = self._rtf_points
        points.append((wall, now))
        while len(points) > 2 and wall - points[0][0] > RTF_WINDOW:
            points.popleft()
        elapsed = wall - points[0][0]
        rtf = round((now - points[0][1]) / elapsed, 2) if elapsed > 1e-6 else None
        mean_ms = sum(self._second_ms) / len(self._second_ms)
        self._second_ms = []
        self.tracer.emit(
            "sim",
            "sim_segundo",
            data={
                "vehiculos": {
                    "carro": self.vcount["carro"],
                    "moto": self.vcount["moto"],
                    "peaton": libsumo.person.getIDCount(),
                },
                "step_ms": round(mean_ms, 3),
                "rtf": rtf,
                "rtf_max": round(1000 / mean_ms, 1) if mean_ms > 0 else None,
            },
            sim_t=now,
        )

    def _checkpoint(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / "checkpoint.xml"
        libsumo.simulation.saveState(str(path))
        self._last_checkpoint = path

    def _reconnect(self, reason: str) -> None:
        """Restart SUMO and resume the scenario: from the current state when the old
        connection still answers (simulated fault), otherwise from the last checkpoint."""
        trace_id = new_trace_id()
        started = time.perf_counter()
        lost_at = None
        resume = None
        try:
            lost_at = libsumo.simulation.getTime()
            if self.state_dir:
                self.state_dir.mkdir(parents=True, exist_ok=True)
                resume = self.state_dir / "reconnect.xml"
                libsumo.simulation.saveState(str(resume))
        except Exception:  # the connection is really gone: use the last checkpoint
            resume = self._last_checkpoint
        self.tracer.emit(
            "sim",
            "error_traci",
            "error",
            data={"motivo": reason, "estrategia": self.strategy},
            sim_t=lost_at,
            trace_id=trace_id,
        )
        try:
            libsumo.close()
        except Exception:
            pass
        libsumo.start(self._sumo_cmd())
        if resume is not None:
            libsumo.simulation.loadState(str(resume))
        now = libsumo.simulation.getTime()
        self.controller.activate(libsumo, self.programs)
        libsumo.simulation.setScale(DEMAND_LEVELS[self.demand])
        if self.accident_lane:
            libsumo.lane.setAllowed(self.accident_lane, ["authority"])
            libsumo.lane.setMaxSpeed(self.accident_lane, 1.0)
        ids = set(libsumo.vehicle.getIDList())
        self.vtype = {v: k for v, k in self.vtype.items() if v in ids}
        for vid in ids - set(self.vtype):
            self.vtype[vid] = VEHICLE_KINDS.get(libsumo.vehicle.getTypeID(vid), "otro")
        self.vcount = Counter(self.vtype.values())
        self._second = -1
        self._rtf_points.clear()
        self.tracer.emit(
            "sim",
            "reconexion",
            data={
                "reanuda_en_t": now,
                "desde": "estado actual"
                if resume and resume.name == "reconnect.xml"
                else ("último checkpoint" if resume else "inicio del escenario"),
                "segundos_perdidos": round(lost_at - now, 1) if lost_at is not None else None,
                "duracion_ms": round((time.perf_counter() - started) * 1000, 1),
            },
            sim_t=now,
            trace_id=trace_id,
        )

    def snapshot(self) -> dict:
        vehicles = []
        waiting = []
        for vid in libsumo.vehicle.getIDList():
            lon, lat = libsumo.simulation.convertGeo(*libsumo.vehicle.getPosition(vid))
            wait = libsumo.vehicle.getWaitingTime(vid)
            waiting.append(wait)
            vehicles.append(
                {
                    "id": vid,
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "type": libsumo.vehicle.getTypeID(vid),
                    "stopped": wait > 0,
                }
            )
        tls = []
        queue_total = 0
        fallback = set(self.fallback_tls)
        for tls_id, lanes in self.tls_lanes.items():
            queue = sum(libsumo.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            queue_total += queue
            tls.append(
                {
                    "id": tls_id,
                    "name": self.names.get(tls_id, tls_id),
                    "state": libsumo.trafficlight.getRedYellowGreenState(tls_id),
                    "queue": queue,
                    "fallback": tls_id in fallback,
                }
            )
        mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else 0.0  # noqa: E731
        return {
            "t": libsumo.simulation.getTime(),
            "run": self.run_id,
            "strategy": self.strategy,
            "demand": self.demand,
            "accident_lane": self.accident_lane,
            "fallback_tls": sorted(fallback),
            "vehicles": vehicles,
            "tls": tls,
            "metrics": {
                "vehicles": len(vehicles),
                "mean_wait_now": mean(waiting),
                "queue": queue_total,
                "arrived": self.arrived,
                "teleports": self.teleports,
                "mean_trip_wait": mean(self.finished_wait),
                "mean_travel_time": mean(self.finished_travel),
            },
        }

    # ---- static geometry for the map -----------------------------------------------------
    def network_geojson(self) -> dict:
        to_lonlat = self.net.convertXY2LonLat
        features = []
        for edge in self.net.getEdges():
            if not edge.allows("passenger"):
                continue
            coords = [list(map(lambda v: round(v, 6), to_lonlat(x, y))) for x, y in edge.getShape()]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "kind": "road",
                        "name": edge.getName(),
                        "lanes": edge.getLaneNumber(),
                        "corridor": edge.getName() == CORRIDOR,
                    },
                }
            )
        for tls in self.net.getTrafficLights():
            streets = sorted({c[0].getEdge().getName() for c in tls.getConnections()} - {""})
            for conn in tls.getConnections():
                lane = conn[0]
                x, y = lane.getShape()[-1]
                lon, lat = to_lonlat(x, y)
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [round(lon, 6), round(lat, 6)],
                        },
                        "properties": {
                            "kind": "signal",
                            "tls": tls.getID(),
                            "index": conn[2],
                            "lane": lane.getID(),
                            "streets": streets,
                            "name": self.names.get(tls.getID(), " / ".join(streets)),
                        },
                    }
                )
        try:
            lane = self.accident_candidate()
            shape = self.net.getLane(lane).getShape()
            x, y = shape[len(shape) // 2]
            lon, lat = to_lonlat(x, y)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                    "properties": {"kind": "accident_site", "lane": lane},
                }
            )
        except ValueError:
            pass
        return {"type": "FeatureCollection", "features": features}
