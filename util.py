import random
from collections.abc import MutableSequence


def shuffle_repeating(dataset: MutableSequence):
    assert isinstance(dataset, MutableSequence)
    while True:
        _dataset = dataset
        random.shuffle(_dataset)
        _dataset.reverse()
        yield from _dataset


if __name__ == "__main__":
    gen = shuffle_repeating(list(range(1, 10)))
    for x in range(1, 100):
        print(next(gen))
