from abc import ABCMeta, abstractmethod


class BaseDriver:
    __metaclass__ = ABCMeta

    @abstractmethod
    def response(self):
        raise NotImplementedError
