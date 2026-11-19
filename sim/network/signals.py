"""Two-phase signal programs for the corridor junctions, replacing netconvert's guesses.

OSM draws Av. Roosevelt and its cross streets as dual carriageways, so one real junction is
several signalised nodes joined into one tls. netconvert then builds a phase for each group
of approaches (27 phases and a 306 s cycle at Cra 34) and signals the median links too
(removed with --tls.uncontrolled-within). A Cali junction of this kind runs a simple cycle:

    corridor green · yellow · all-red · cross-street green · yellow · all-red

Every controlled vehicle link is assigned by the street name of its incoming edge (the
corridor, everything else is the cross street). Straight links get priority (G), turns yield
(g). A pedestrian crossing gets green while the street it crosses has red. Timings below are
the project's design values (90 s cycle, more green for the corridor), not field data."""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

CORRIDOR = "Calle 6"
CYCLE = 90
YELLOW = 3
ALL_RED = 2
CORRIDOR_GREEN = 50
CROSS_GREEN = CYCLE - CORRIDOR_GREEN - 2 * (YELLOW + ALL_RED)


def _signal_links(root: ET.Element) -> dict[str, dict[int, tuple[str, str, str]]]:
    """tls id -> link index -> (kind, group, dir): kind vehicle|pedestrian, group corridor|cross
    (for a crossing, the street it crosses), dir as in the connection (s straight)."""
    edges = {e.get("id"): e for e in root.iter("edge")}
    out: dict[str, dict[int, tuple[str, str, str]]] = {}
    for conn in root.iter("connection"):
        tl = conn.get("tl")
        if tl is None:
            continue
        index = int(conn.get("linkIndex"))
        crossing = next(
            (
                edges[e]
                for e in (conn.get("to"), conn.get("from"))
                if edges.get(e) is not None and edges[e].get("function") == "crossing"
            ),
            None,
        )
        if crossing is not None:
            crossed = [edges[e].get("name", "") for e in crossing.get("crossingEdges").split()]
            group = "corridor" if CORRIDOR in crossed else "cross"
            out.setdefault(tl, {})[index] = ("pedestrian", group, "s")
        else:
            name = edges[conn.get("from")].get("name", "")
            group = "corridor" if name == CORRIDOR else "cross"
            out.setdefault(tl, {})[index] = ("vehicle", group, conn.get("dir"))
    return out


def phase_state(links: dict[int, tuple], green: str | None, yellow: str | None) -> str:
    """Signal string for one phase: `green` group may go, `yellow` group is clearing."""
    state = []
    for index in range(max(links) + 1):
        if index not in links:  # unused index: always red
            state.append("r")
            continue
        kind, group, direction = links[index]
        if kind == "pedestrian":
            # pedestrians cross a street while that street's vehicles are held
            other = "cross" if group == "corridor" else "corridor"
            state.append("G" if green == other else "r")
        elif group == green:
            state.append("G" if direction == "s" else "g")
        elif group == yellow:
            state.append("y")
        else:
            state.append("r")
    return "".join(state)


def programs(net_file: Path) -> dict[str, list[tuple[int, str]]]:
    root = ET.parse(net_file).getroot()
    result = {}
    for tl, links in _signal_links(root).items():
        result[tl] = [
            (CORRIDOR_GREEN, phase_state(links, "corridor", None)),
            (YELLOW, phase_state(links, None, "corridor")),
            (ALL_RED, phase_state(links, None, None)),
            (CROSS_GREEN, phase_state(links, "cross", None)),
            (YELLOW, phase_state(links, None, "cross")),
            (ALL_RED, phase_state(links, None, None)),
        ]
    return result


def apply(net_file: Path) -> None:
    """Write the programs into the network's own <tlLogic> elements. Reloading the network
    with netconvert -s would drop the signal of some crossings inside joined junctions, and
    netconvert cannot load programs while importing OSM (the joined ids do not exist yet)."""
    new = programs(net_file)

    def replace(match: re.Match) -> str:
        tl = re.search(r'id="([^"]+)"', match.group(1)).group(1)
        phases = "".join(f'        <phase duration="{d}" state="{s}"/>\n' for d, s in new[tl])
        return f"{match.group(1)}\n{phases}    </tlLogic>"

    # text substitution keeps the rest of the file (and netconvert's header) byte for byte
    text = net_file.read_text(encoding="utf-8")
    net_file.write_text(
        re.sub(r"(<tlLogic [^>]*>).*?</tlLogic>", replace, text, flags=re.S), encoding="utf-8"
    )


def current_programs(net_file: Path) -> dict[str, list[tuple[int, str]]]:
    root = ET.parse(net_file).getroot()
    return {
        tl.get("id"): [(int(float(p.get("duration"))), p.get("state")) for p in tl.iter("phase")]
        for tl in root.iter("tlLogic")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, default=Path("scenarios/roosevelt4/roosevelt4.net.xml"))
    args = parser.parse_args()
    for tl, phases in current_programs(args.net).items():
        print(tl)
        for duration, state in phases:
            print(f"  {duration:3d} s  {state}")


if __name__ == "__main__":
    main()
