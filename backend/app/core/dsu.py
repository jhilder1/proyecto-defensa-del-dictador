"""Disjoint-Set Union (Union-Find) with path compression and union by rank."""

from typing import Generic, TypeVar, Dict, List, Optional

T = TypeVar("T")


class DisjointSetUnion(Generic[T]):
    """Disjoint Set Union (DSU) data structure.
    
    Provides near-constant time operations O(alpha(V)) for set membership and union.
    """

    def __init__(self, elements: Optional[List[T]] = None):
        self.parent: Dict[T, T] = {}
        self.rank: Dict[T, int] = {}
        if elements:
            for elem in elements:
                self.make_set(elem)

    def make_set(self, x: T) -> None:
        """Initializes a new singleton set with element x."""
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: T) -> T:
        """Finds representative of the set containing x with path compression."""
        if x not in self.parent:
            self.make_set(x)
            return x

        # Path compression
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        curr = x
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt

        return root

    def union(self, x: T, y: T) -> bool:
        """Unites the sets containing x and y using union by rank.
        
        Returns:
            bool: True if elements were in different sets and merged; False if already in the same set.
        """
        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return False

        # Union by rank
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1

        return True

    def connected(self, x: T, y: T) -> bool:
        """Checks if x and y belong to the same set."""
        return self.find(x) == self.find(y)

    def get_components(self) -> Dict[T, List[T]]:
        """Returns mapping from set root to list of members in that component."""
        components: Dict[T, List[T]] = {}
        for elem in self.parent:
            root = self.find(elem)
            if root not in components:
                components[root] = []
            components[root].append(elem)
        return components

