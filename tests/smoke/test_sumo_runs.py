import sys

import libsumo
import sumolib


def test_python_is_311():
    assert sys.version_info[:2] == (3, 11)


def test_grid_has_four_traffic_lights(grid_cfg):
    net_file = grid_cfg.parent / "grid2x2.net.xml"
    net = sumolib.net.readNet(str(net_file), withPedestrianConnections=True)
    assert len(net.getTrafficLights()) == 4


def test_sumo_runs_300_steps_headless(grid_cfg):
    libsumo.start(["sumo", "-c", str(grid_cfg), "--no-step-log", "--no-warnings"])
    try:
        departed = 0
        for _ in range(300):
            libsumo.simulationStep()
            departed += libsumo.simulation.getDepartedNumber()
        assert libsumo.simulation.getTime() == 300
        assert departed > 0
        assert len(libsumo.trafficlight.getIDList()) == 4
    finally:
        libsumo.close()
