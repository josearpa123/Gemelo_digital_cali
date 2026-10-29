"""Live simulation runner used by sim-api: one libsumo simulation, swappable strategies,
events (accident, demand level) and a JSON-friendly snapshot per step.

All methods must be called from the same thread (libsumo is not thread-safe)."""

from collections import deque
from pathlib import Path

import libsumo
import sumolib

from sim.controllers import FixedTimeController, MaxPressureController
from sim.controllers.base import Controller
from sim.controllers.rl_policy import RLController, find_model

DEMAND_LEVELS = {"valley": 0.45, "peak": 1.0, "peak_plus": 1.3}
CORRIDOR = "Calle 6"


class SimRunner:
    def __init__(
        self, net_file: Path, route_file: Path, seed: int = 0, sumo_args: list[str] | None = None
    ):
        self.net_file = Path(net_file)
        self.sumo_args = list(sumo_args or [])
        self.route_file = Path(route_file)
        self.seed = seed
        self.net = sumolib.net.readNet(str(self.net_file), withPedestrianConnections=True)
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
            strategies["rl"] = lambda: RLController(str(self.net_file), model)
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
    def start(self, strategy: str | None = None) -> None:
        if self.running:
            libsumo.close()
        strategy = strategy or self.strategy
        libsumo.start(
            [
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
        )
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
        self.demand = "peak"
        self.trip_wait: dict[str, float] = {}
        self.depart_time: dict[str, float] = {}
        self.finished_wait: deque[float] = deque(maxlen=2000)
        self.finished_travel: deque[float] = deque(maxlen=2000)
        self.arrived = 0
        self.teleports = 0
        self.strategy = None
        self.set_strategy(strategy)

    def close(self) -> None:
        if self.running:
            libsumo.close()
            self.running = False

    def set_strategy(self, strategy: str) -> None:
        if strategy not in self.strategies:
            raise ValueError(f"strategy not available: {strategy}")
        if self.strategy is not None:
            self.controller.deactivate(libsumo, self.programs)
        self.controller = self.strategies[strategy]()
        self.controller.activate(libsumo, self.programs)
        self.strategy = strategy

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

    def set_accident(self, active: bool, lane: str | None = None) -> None:
        if active and self.accident_lane is None:
            lane = lane or self.accident_candidate()
            self._accident_allowed = list(libsumo.lane.getAllowed(lane))
            libsumo.lane.setAllowed(lane, ["authority"])
            libsumo.lane.setMaxSpeed(lane, 1.0)
            self.accident_lane = lane
        elif not active and self.accident_lane is not None:
            lane = self.accident_lane
            libsumo.lane.setAllowed(lane, self._accident_allowed)
            libsumo.lane.setMaxSpeed(lane, self.net.getLane(lane).getSpeed())
            self.accident_lane = None

    def set_demand(self, level: str) -> None:
        libsumo.simulation.setScale(DEMAND_LEVELS[level])
        self.demand = level

    # ---- stepping ---------------------------------------------------------------------
    def step(self) -> None:
        self.controller.step(libsumo)
        libsumo.simulationStep()
        self.controller.after_step()
        now = libsumo.simulation.getTime()
        self.teleports += libsumo.simulation.getStartingTeleportNumber()
        for vid in libsumo.simulation.getDepartedIDList():
            self.depart_time[vid] = now
        for vid in libsumo.vehicle.getIDList():
            self.trip_wait[vid] = libsumo.vehicle.getAccumulatedWaitingTime(vid)
        for vid in libsumo.simulation.getArrivedIDList():
            self.arrived += 1
            self.finished_wait.append(self.trip_wait.pop(vid, 0.0))
            if vid in self.depart_time:
                self.finished_travel.append(now - self.depart_time.pop(vid))

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
        for tls_id, lanes in self.tls_lanes.items():
            queue = sum(libsumo.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            queue_total += queue
            tls.append(
                {
                    "id": tls_id,
                    "state": libsumo.trafficlight.getRedYellowGreenState(tls_id),
                    "queue": queue,
                }
            )
        mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else 0.0  # noqa: E731
        return {
            "t": libsumo.simulation.getTime(),
            "run": self.run_id,
            "strategy": self.strategy,
            "demand": self.demand,
            "accident_lane": self.accident_lane,
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
