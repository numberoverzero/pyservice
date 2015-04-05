import os
import ujson

HERE = os.path.abspath(os.path.dirname(__file__))


def load_api(filename):
    '''
    Helper to load api specifications in the examples folder.

    Returns a nested dict appropriate for unpacking into Client or Service
    '''
    api_filename = os.path.join(HERE, filename)
    with open(api_filename) as api_file:
        api = ujson.loads(api_file.read())
    return api
