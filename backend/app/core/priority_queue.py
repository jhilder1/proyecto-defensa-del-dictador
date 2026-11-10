"""Custom Min-Heap Priority Queue implementation from scratch (without heapq)."""

from typing import Generic, TypeVar, List, Tuple, Any, Optional

T = TypeVar("T")


class PriorityQueue(Generic[T]):
    """Min-Heap implementation supporting push, pop, peek, and length checks.
    
    Elements are stored as comparable items (e.g. tuples (priority, tie_breaker, data)).
    Time Complexity:
        Push: O(log N)
        Pop: O(log N)
        Peek: O(1)
    """

    def __init__(self):
        self._heap: List[T] = []

    def __len__(self) -> int:
        return len(self._heap)

    def is_empty(self) -> bool:
        return len(self._heap) == 0

    def push(self, item: T) -> None:
        """Pushes an item onto the min-heap."""
        self._heap.append(item)
        self._sift_up(len(self._heap) - 1)

    def pop(self) -> T:
        """Removes and returns the minimum element from the heap."""
        if self.is_empty():
            raise IndexError("pop from an empty priority queue")

        min_val = self._heap[0]
        last_val = self._heap.pop()

        if self._heap:
            self._heap[0] = last_val
            self._sift_down(0)

        return min_val

    def peek(self) -> T:
        """Returns the minimum element without removing it."""
        if self.is_empty():
            raise IndexError("peek from an empty priority queue")
        return self._heap[0]

    def _sift_up(self, idx: int) -> None:
        """Moves element at idx up to maintain the min-heap invariant."""
        parent = (idx - 1) // 2
        while idx > 0 and self._heap[idx] < self._heap[parent]:
            self._heap[idx], self._heap[parent] = self._heap[parent], self._heap[idx]
            idx = parent
            parent = (idx - 1) // 2

    def _sift_down(self, idx: int) -> None:
        """Moves element at idx down to maintain the min-heap invariant."""
        size = len(self._heap)
        while True:
            left = 2 * idx + 1
            right = 2 * idx + 2
            smallest = idx

            if left < size and self._heap[left] < self._heap[smallest]:
                smallest = left

            if right < size and self._heap[right] < self._heap[smallest]:
                smallest = right

            if smallest != idx:
                self._heap[idx], self._heap[smallest] = self._heap[smallest], self._heap[idx]
                idx = smallest
            else:
                break

