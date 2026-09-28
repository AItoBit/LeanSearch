from __future__ import annotations

import heapq
import itertools
from collections import deque

from leansearch.search.base import Searcher
from leansearch.search.node import SearchNode


class GreedySearch(Searcher):
    """Commit to the best-scoring child at every step; no backtracking."""

    algorithm = "greedy"

    def run(self, root: SearchNode) -> None:
        node = root
        while not self.done():
            children = self.expand(node)
            if self.solution is not None or not children:
                return
            node = max(children, key=lambda n: n.search_score)


class BreadthFirstSearch(Searcher):
    algorithm = "bfs"

    def run(self, root: SearchNode) -> None:
        queue = deque([root])
        while queue and not self.done():
            queue.extend(self.expand(queue.popleft()))


class BeamSearch(Searcher):
    """Keep the `beam_width` best states at each depth."""

    algorithm = "beam"

    def __init__(self, *args, beam_width: int = 8, **kwargs):
        super().__init__(*args, **kwargs)
        self.beam_width = beam_width

    def run(self, root: SearchNode) -> None:
        beam = [root]
        while beam and not self.done():
            candidates: list[SearchNode] = []
            for node in beam:
                candidates += self.expand(node)
                if self.done():
                    return
            beam = sorted(candidates, key=lambda n: n.search_score, reverse=True)[: self.beam_width]

    def describe(self) -> dict[str, object]:
        return {**super().describe(), "beam_width": self.beam_width}


class BestFirstSearch(Searcher):
    """Global priority queue over all open states, ordered by search score."""

    algorithm = "best_first"

    def run(self, root: SearchNode) -> None:
        counter = itertools.count()
        heap = [(-root.search_score, next(counter), root)]
        while heap and not self.done():
            _, _, node = heapq.heappop(heap)
            for child in self.expand(node):
                heapq.heappush(heap, (-child.search_score, next(counter), child))


ALGORITHMS: dict[str, type[Searcher]] = {
    "greedy": GreedySearch,
    "bfs": BreadthFirstSearch,
    "beam": BeamSearch,
    "best_first": BestFirstSearch,
}
