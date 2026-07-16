"""Minimal stub of langgraph.graph used for local tests.

This provides START, END, and a very small StateGraph/CompiledGraph
implementation so the project's pipeline can be executed in tests
without installing the real langgraph package.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# Sentinels used by pipeline.py
START = "__START__"
END = "__END__"


class StateGraph:
    def __init__(self, state_type: Optional[type] = None):
        self._nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._edges: Dict[str, List[str]] = {}
        self._conditional: Dict[str, Tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]] = {}

    def add_node(self, name: str, func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self._nodes[name] = func

    def add_edge(self, src: str, dst: str):
        self._edges.setdefault(src, []).append(dst)

    def add_conditional_edges(self, node: str, route_func: Callable[[Dict[str, Any]], str], mapping: Dict[str, str]):
        self._conditional[node] = (route_func, mapping)

    def compile(self):
        return CompiledGraph(self._nodes, self._edges, self._conditional)


class CompiledGraph:
    def __init__(self, nodes: Dict[str, Callable], edges: Dict[str, List[str]], conditional: Dict[str, Tuple[Callable, Dict[str, str]]]):
        self._nodes = nodes
        self._edges = edges
        self._conditional = conditional

    def get_graph(self):
        return self

    def draw_mermaid(self):
        return "flowchart TD\n  START --> planner --> designer --> coder --> reviewer --> assembler --> tester --> END"

    def invoke(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        state = dict(initial_state)
        current = START

        # simple loop: follow edges; if conditional node, call route function
        while True:
            if current == END:
                break

            # choose next node from edges mapping
            # if current is a special START node, just use edges[START]
            next_node = None

            # if there is an edge from current and it's the only one, pick it
            if current in self._edges and self._edges[current]:
                next_node = self._edges[current][0]

            # if the next_node is a registered node, execute it
            if next_node and next_node in self._nodes:
                fn = self._nodes[next_node]
                try:
                    delta = fn(state) or {}
                except TypeError:
                    # some nodes may be defined to accept no args
                    delta = fn()
                if isinstance(delta, dict):
                    state.update(delta)
                current = next_node
                continue

            # handle conditional nodes (node itself triggers routing)
            if current in self._conditional:
                route_func, mapping = self._conditional[current]
                key = route_func(state)
                chosen = mapping.get(key)
                if not chosen:
                    raise RuntimeError(f"No mapping for route key: {key}")
                # execute chosen node
                fn = self._nodes.get(chosen)
                if fn:
                    delta = fn(state) or {}
                    state.update(delta)
                current = chosen
                continue

            # if no edges found from current, try to advance by finding START edge
            if current == START and START in self._edges and self._edges[START]:
                current = START  # loop will pick edges[START]
                # set current to START so above logic executes
                # pick next in next iteration
                # but to avoid infinite loop, pick first
                nxt = self._edges[START][0]
                fn = self._nodes.get(nxt)
                if fn:
                    delta = fn(state) or {}
                    state.update(delta)
                current = nxt
                continue

            # fallback: if no more nodes, stop
            break

        return state
