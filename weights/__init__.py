from functools import reduce

import h5py
import numpy as np


def load_weights(*weights_names):
    weights = list()
    for weights_name in weights_names:
        filepath = "weights/%s.h5" % weights_name
        with h5py.File(filepath, 'r') as file:
            w = walk(file, lambda _, x: np.array(x))
            weights.append(w)
    return weights if len(weights) > 1 else weights[0]


def walk(dictionary, collect, key_chain=None):
    result = {}
    for key, item in dictionary.items():
        sub_key_chain = (key_chain if key_chain is not None else []) + [key]
        if callable(getattr(item, "items", None)):
            result[key] = walk(item, collect, key_chain=sub_key_chain)
        else:
            result[key] = collect(sub_key_chain, item)
    return result


def walk_key_chain(dictionary, key_chain):
    """
    Walks down the nesting structure of a dictionary, following the keys in the `key_chain`.

    Example:
        d = {'a':
              {'b':
                {'c': 15}
              }
            }
        __walk_key_chain(d, ['a', 'b', 'c'])  # returns 15
    :param dictionary: a nested dictionary containing other dictionaries
    :param key_chain: a list of keys to traverse down the nesting structure
    :return: the value in the nested structure after traversing down the `key_chain`
    """
    return reduce(lambda d, k: d[k], key_chain, dictionary)