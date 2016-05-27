from collections import OrderedDict

from marshmallow import schema
from six import iteritems

from slyd.orm.decorators import pre_dump, post_dump, pre_load, post_load
from slyd.orm.exceptions import ValidationError

__all__ = [
    'BaseFileSchema',
]


class FileSchemaOpts(schema.SchemaOpts):
    def __init__(self, meta):
        super(FileSchemaOpts, self).__init__(meta)
        if meta is schema.BaseSchema.Meta:
            return

        # make marshmallow use OrderedDicts, so that collections of enveloped
        # objects maintain their order when loaded
        self.ordered = True
        # the model from which the Schema was created, required
        self.model = getattr(meta, 'model')
        # whether to wrap the output in an envelope keyed by primary key
        self.envelope = getattr(meta, 'envelope', False)
        if not isinstance(self.envelope, bool):
            raise ValueError("'envelope' option must be a boolean.")
        # whether to remove the key from the body of the enveloped object
        self.envelope_remove_key = getattr(meta, 'envelope_remove_key', False)
        if not isinstance(self.envelope_remove_key, bool):
            raise ValueError("'envelope_remove_key' option must be a boolean.")


class BaseFileSchema(schema.Schema):
    OPTIONS_CLASS = FileSchemaOpts

    def __getattr__(self, item):
        # try to resolve missing attributes from the model
        return getattr(self.opts.model, item)

    def get_attribute(self, attr, obj, default):
        return super(BaseFileSchema, self).get_attribute(attr, obj, default)

    @pre_load(pass_many=True)
    def unwrap_envelopes(self, data, many):
        if self.opts.envelope:
            unwrapped = []
            for pk, obj in iteritems(data):
                if not self.opts.envelope_remove_key:
                    try:
                        if obj[self.opts.model._pk_field] != pk:
                            raise ValidationError(
                                u"Envelope id does not match value of primary key "
                                u"field")
                    except KeyError:
                        pass
                obj[self.opts.model._pk_field] = pk
                unwrapped.append(obj)
            if not many and len(unwrapped) == 1:
                return unwrapped[0]
            return unwrapped
        return data

    @post_load
    def create_object(self, data):
        storage = self.context.get('storage', None)
        model = self.opts.model(storage, snapshots=('committed',), **data)
        return model.with_snapshots()

    @pre_dump
    def select_snapshots(self, instance):
        snapshots = self.context.get('snapshots', None)
        if snapshots is not None:
            instance = instance.with_snapshots(snapshots)
        return instance

    @post_dump
    def order_keys(self, data):
        """
        Create ordered dictionaries sorted by key. We do this here instead of
        using the sort_keys parameter of json.dumps, so that object keys are
        sorted, while collections can maintain their insertion order
        """
        return OrderedDict((item for item in sorted(iteritems(data))))

    @post_dump(pass_many=True)
    def wrap_envelopes(self, data, many):
        if self.opts.envelope:
            if not many:
                data = [data]
            wrapped = OrderedDict()
            for obj in data:
                pk_field = self.opts.model._pk_field
                pk = obj[pk_field]
                if self.opts.envelope_remove_key:
                    del obj[pk_field]
                wrapped[pk] = obj
            return wrapped
        return data

    def _do_load(self, data, many=None, *args, **kwargs):
        # we need to wrap the result of a many load in a ModelCollection, but
        # post_load(pass_many=True) processors are called before the Model
        # instances are created in the post_load(pass_many=False) processor
        result, errors = super(BaseFileSchema, self)._do_load(
            data, many, *args, **kwargs)
        if many:
            result = self.opts.model.collection(result)
        return result, errors
