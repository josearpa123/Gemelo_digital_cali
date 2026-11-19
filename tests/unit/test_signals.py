from pathlib import Path

import pytest

from sim.network import signals

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")

LINKS = {
    0: ("vehicle", "corridor", "s"),
    1: ("vehicle", "corridor", "l"),
    2: ("vehicle", "cross", "s"),
    3: ("pedestrian", "corridor", "s"),  # crosses the corridor
    4: ("pedestrian", "cross", "s"),  # crosses the cross street
    6: ("vehicle", "cross", "r"),  # index 5 unused
}


def test_corridor_green_holds_cross_street_and_lets_its_pedestrians_walk():
    # straight G, turn yields g, cross street red, only the crossing over the cross street walks
    assert signals.phase_state(LINKS, "corridor", None) == "GgrrGrr"
    assert signals.phase_state(LINKS, "cross", None) == "rrGGrrg"


def test_clearance_phases_never_show_green():
    assert signals.phase_state(LINKS, None, "corridor") == "yyrrrrr"
    assert signals.phase_state(LINKS, None, None) == "rrrrrrr"


@pytest.mark.skipif(not NET.exists(), reason="run python -m sim.network.build_osm first")
def test_roosevelt4_runs_the_two_phase_cycle_on_every_junction():
    current = signals.current_programs(NET)
    assert len(current) == 4
    assert current == signals.programs(NET)
    for phases in current.values():
        assert [d for d, _ in phases] == [
            signals.CORRIDOR_GREEN,
            signals.YELLOW,
            signals.ALL_RED,
            signals.CROSS_GREEN,
            signals.YELLOW,
            signals.ALL_RED,
        ]
        assert sum(d for d, _ in phases) == signals.CYCLE
        corridor, cross = phases[0][1], phases[3][1]
        # every controlled link gets green in exactly one of the two phases (or none if unused)
        assert not any(a in "Gg" and b in "Gg" for a, b in zip(corridor, cross, strict=True))
