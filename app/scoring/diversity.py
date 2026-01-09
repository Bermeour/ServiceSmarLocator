from dataclasses import dataclass
from typing import List, Tuple, Set


@dataclass
class SuggestionItem:
    type: str
    value: str
    score: int
    reason: str


@dataclass
class NodeGroup:
    node_key: str
    suggestions: List[SuggestionItem]

    @property
    def best_score(self) -> int:
        if not self.suggestions:
            return -999
        return max(s.score for s in self.suggestions)


class SuggestionDiversifier:
    """
    Agrupa suggestions por 'nodo' y devuelve:
    - top_nodes: cuantos nodos distintos retornar
    - top_per_node: cuantas suggestions máximo por nodo
    """

    def __init__(self, top_nodes: int = 5, top_per_node: int = 2):
        self.top_nodes = top_nodes
        self.top_per_node = top_per_node

    def diversify(self, groups: List[NodeGroup]) -> List[SuggestionItem]:
        # Ordena nodos por su mejor score
        groups_sorted = sorted(groups, key=lambda g: g.best_score, reverse=True)

        # Tomar top nodos
        selected = groups_sorted[: self.top_nodes]

        # Aplanar suggestions, pero deduplicando por (type,value)
        out: List[SuggestionItem] = []
        seen: Set[Tuple[str, str]] = set()

        for g in selected:
            # Ordena suggestions del nodo por score
            sug_sorted = sorted(g.suggestions, key=lambda s: s.score, reverse=True)
            sug_sorted = sug_sorted[: self.top_per_node]

            for s in sug_sorted:
                key = (s.type, s.value)
                if key in seen:
                    continue
                seen.add(key)
                out.append(s)

        # Orden final por score descendente para que SmartFind pruebe mejor primero
        out.sort(key=lambda s: s.score, reverse=True)
        return out
