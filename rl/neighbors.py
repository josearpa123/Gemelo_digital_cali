"""Neighbouring traffic lights: tls reachable by road within a distance, in either direction."""

import heapq
from functools import lru_cache

import sumolib

MAX_DISTANCE = 600.0


@lru_cache(maxsize=8)
def neighbor_map(net_file: str, max_distance: float = MAX_DISTANCE) -> dict[str, tuple[str, ...]]:
    net = sumolib.net.readNet(net_file)
    node_tls: dict[str, str] = {}
    for tls in net.getTrafficLights():
        for conn in tls.getConnections():
            node_tls[conn[0].getEdge().getToNode().getID()] = tls.getID()

    links: dict[str, set[str]] = {t.getID(): set() for t in net.getTrafficLights()}
    for start_node, tls_id in node_tls.items():
        # Dijkstra downstream from every node of this tls
        queue = [(0.0, start_node)]
        seen = {start_node}
        while queue:
            dist, node_id = heapq.heappop(queue)
            for edge in net.getNode(node_id).getOutgoing():
                if not edge.allows("passenger"):
                    continue
                nxt = edge.getToNode().getID()
                nd = dist + edge.getLength()
                if nd > max_distance or nxt in seen:
                    continue
                seen.add(nxt)
                other = node_tls.get(nxt)
                if other is not None and other != tls_id:
                    links[tls_id].add(other)
                    links[other].add(tls_id)
                    continue
                heapq.heappush(queue, (nd, nxt))
    return {t: tuple(sorted(n)) for t, n in links.items()}
