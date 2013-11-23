

class Service(object):
    def __init__(self, description, **config):
        self.description = description
        self._run_config = {}
        self._init_config = config

    def _attr(self, key, default):
        '''Load value - presedence is run config -> init config -> description meta -> default'''
        value = self._run_config.get(key, None)
        value = value or self._init_config.get(key, None)
        value = value or self.description.metadata.get(key, None)
        return value or default
