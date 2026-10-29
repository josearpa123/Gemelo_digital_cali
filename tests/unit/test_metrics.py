import math

import pytest

from eval.metrics import approach_metrics, jain, read_tripinfo, trip_metrics

TRIPINFO = """<tripinfos>
    <tripinfo id="a" vType="car" arrival="120.00" duration="100.00" waitingTime="20.00"/>
    <tripinfo id="b" vType="moto" arrival="90.00" duration="60.00" waitingTime="0.00"/>
    <tripinfo id="c" vType="car" arrival="-1" duration="200.00" waitingTime="40.00"/>
</tripinfos>
"""


def test_jain_all_equal_is_one():
    assert jain([7, 7, 7, 7]) == pytest.approx(1.0)


def test_jain_single_user_is_one_over_n():
    assert jain([10, 0, 0, 0, 0]) == pytest.approx(1 / 5)


def test_jain_known_value():
    assert jain([1, 2, 3]) == pytest.approx(36 / (3 * 14))


def test_jain_edge_cases():
    assert jain([0, 0]) == 1.0
    assert math.isnan(jain([]))


def test_trip_metrics_include_unfinished(tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text(TRIPINFO)
    assert [t["finished"] for t in read_tripinfo(path)] == [True, True, False]
    m = trip_metrics(path)
    assert m["trips"] == 3 and m["unfinished"] == 1
    assert m["mean_travel_time"] == pytest.approx(120.0)
    assert m["mean_wait"] == pytest.approx(20.0)


def test_approach_metrics():
    m = approach_metrics(
        wait_s={"n": 100.0, "e": 100.0, "s": 0.0},
        vehicles={"n": {"1", "2"}, "e": {"3", "4"}, "s": set()},
        queue_sum={"n": 30, "e": 10, "s": 0},
        queue_max={"n": 4, "e": 2, "s": 0},
        steps=10,
    )
    assert m["jain_wait"] == pytest.approx(1.0)
    assert m["approaches"] == 2
    assert m["queue_mean"] == pytest.approx(40 / 30)
    assert m["queue_max"] == 4
