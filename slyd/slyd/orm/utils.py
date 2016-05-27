from django.utils.functional import cached_property

from slyd.orm.exceptions import ValidationError

__all__ = [
    'cached_property',
    'unspecified',
    'validate_type',
    'AttributeDict',
]


unspecified = object()


def validate_type(value, model):
    if not isinstance(value, model):
        raise ValidationError(
            "'{!r}' is not an instance of type '{}'".format(
                value, model.__name__))


class AttributeDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                u"'{}' object has no attribute '{}'".format(
                    self.__class__.__name__, name))
