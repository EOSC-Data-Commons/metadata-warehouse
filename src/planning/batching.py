from collections.abc import Iterable
from typing import NamedTuple


class BatchRange(NamedTuple):
    """A batch of harvest events, described by its first and last id (inclusive) and its size.

    Harvest events of one run are ordered by id, so a batch can be loaded again later with
    `id BETWEEN first_id AND last_id`. This keeps the description tiny (it is passed around as an Airflow XCom),
    instead of carrying the XML of all records.
    """

    first_id: str
    last_id: str
    size: int


def chunk_ranges(ids: Iterable[str], batch_size: int) -> list[BatchRange]:
    """Splits a sorted stream of ids into consecutive ranges of `batch_size` ids (the last one may be smaller)."""
    if batch_size < 1:
        raise ValueError(f'batch_size must be >= 1, got {batch_size}')

    ranges: list[BatchRange] = []
    first: str | None = None
    last: str | None = None
    size = 0

    for id_ in ids:
        if first is None:
            first = id_
        last = id_
        size += 1

        if size == batch_size:
            ranges.append(BatchRange(first_id=first, last_id=last, size=size))
            first, last, size = None, None, 0

    if first is not None and last is not None:
        ranges.append(BatchRange(first_id=first, last_id=last, size=size))

    return ranges
