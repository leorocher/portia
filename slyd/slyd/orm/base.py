from collections import OrderedDict
from itertools import chain
import json
from weakref import WeakKeyDictionary

from six import iteritems, iterkeys, string_types, with_metaclass

from slyd.orm.collection import ModelCollection
from slyd.orm.exceptions import ImproperlyConfigured, PathResolutionError
from slyd.orm.fields import Field
from slyd.orm.registry import models
from slyd.orm.relationships import BaseRelationship
from slyd.orm.schemas import BaseFileSchema
from slyd.orm.snapshots import ModelSnapshots
from slyd.orm.utils import cached_property, unspecified, AttributeDict
from slyd.utils.storage import ContentFile

__all__ = [
    'Model',
]


class ModelOpts(object):
    """Meta options for Models."""
    def __init__(self, meta, model):
        self.path = getattr(meta, 'path', None)
        if self.path is not None and not isinstance(self.path, string_types):
            raise ValueError("'path' option must be a string or None.")
        self.owner = getattr(meta, 'owner', False)
        if self.owner != False and not isinstance(self.owner, string_types):
            raise ValueError("'many' option must be a string or False.")
        if self.owner and not isinstance(model._fields.get(self.owner),
                                         BaseRelationship):
            raise ValueError("'many' option must be a relationship name.")
        self.envelope = getattr(meta, 'envelope', False)
        if not isinstance(self.envelope, bool):
            raise ValueError("'envelope' option must be a boolean.")


class ModelMeta(type):
    """Meta class for models"""
    def __new__(mcs, name, bases, attrs):
        parents = [b for b in bases if isinstance(b, ModelMeta)]
        if not parents:
            return super(ModelMeta, mcs).__new__(mcs, name, bases, attrs)

        # check if a model with the same name exists in the registry
        if name in models:
            raise ImproperlyConfigured(
                u"A Model named '{}' already exists".format(name))

        meta = attrs.pop('Meta', None)
        primary_key = None
        fields = {}
        basic_attrs = {}
        file_schema_attrs = {}

        for attrname, value in iteritems(attrs):
            if isinstance(value, BaseRelationship):
                fields[attrname] = value
            elif isinstance(value, Field):
                if value.primary_key:
                    if primary_key:
                        raise ImproperlyConfigured(
                            u"Model '{}' declared with more than one primary "
                            u"key".format(name))
                    primary_key = attrname
                fields[attrname] = value
            # move decorated marshmallow methods to the file schema
            elif hasattr(value, '__marshmallow_tags__'):
                file_schema_attrs[attrname] = value
            else:
                basic_attrs[attrname] = value

        if fields and not primary_key:
            raise ImproperlyConfigured(
                u"Model '{}' declared with no primary key".format(name))

        cls = super(ModelMeta, mcs).__new__(mcs, name, bases, basic_attrs)
        cls._pk_field = primary_key
        cls._fields = fields
        cls._file_fields = file_fields = {k for k, f in iteritems(fields)
                                          if not f.ignore_in_file}
        cls.opts = ModelOpts(meta, cls)
        cls.collection = type(name + 'Collection', (ModelCollection,), {
            'model': cls
        })

        for attrname, field in iteritems(fields):
            if attrname in file_fields:
                file_schema_attrs[attrname] = field
            field.contribute_to_class(cls, attrname)

        # build a marshmallow schema for the filesystem format
        meta_bases = (meta, object) if meta else (object,)
        file_schema_attrs['Meta'] = type('Meta', meta_bases, {
            'model': cls
        })
        cls.file_schema = type(cls.__name__ + 'Schema', (BaseFileSchema,),
                               file_schema_attrs)

        # add new model to registry by name
        models[name] = cls
        return cls

    @property
    def _file_model(cls):
        """Find the top-level model stored in this model's path."""
        model = getattr(cls, '_cached_file_model', unspecified)
        if model is not unspecified:
            return model

        path = cls.opts.path
        model = cls
        while True:
            if model.opts.owner:
                try:
                    owner = model._fields[model.opts.owner].model
                    if owner is not model and owner.opts.path == path:
                        model = owner
                        continue
                except KeyError:
                    pass
            cls._cached_file_model = model
            return model


class Model(with_metaclass(ModelMeta)):
    _own_attributes = {'data_key', 'storage', 'snapshots', '_initializing'}

    # set by metaclass
    _fields = None
    _file_fields = None
    _pk_field = None
    collection = None
    file_schema = None
    opts = None

    # share data between instances of the same model, to simplify relationships
    shared_data_store = WeakKeyDictionary()
    # keeps track of files that are loading
    loaded = WeakKeyDictionary()

    snapshot_class = ModelSnapshots

    class Meta:
        pass

    def __init__(self, storage=None, snapshots=None, _data_key=unspecified,
                 **kwargs):
        if _data_key is unspecified:
            if self._pk_field not in kwargs:
                raise TypeError(
                    u"Model '{}' must be initialized with a value for the '{}' "
                    u"field".format(self.__class__.__name__, self._pk_field))
            _data_key = self.__class__, kwargs[self._pk_field]

        self.data_key = _data_key
        self.storage = storage
        self.snapshots = snapshots or ModelSnapshots.default_snapshots
        self._initializing = set(kwargs.keys())

        # TODO: initialize dependant fields after their dependencies
        fields = []
        relationships = []

        for attrname in iterkeys(kwargs):
            if attrname in self._fields:
                field = self._fields[attrname]
                if isinstance(field, BaseRelationship):
                    relationships.append(attrname)
                elif isinstance(field, Field):
                    fields.append(attrname)
            else:
                raise TypeError(
                    u"'{}' is not a field of model '{}'".format(
                        attrname, self.__class__.__name__))

        # set relationships last since they may depend on other fields
        for attrname in fields:
            setattr(self, attrname, kwargs[attrname])
        for attrname in relationships:
            setattr(self, attrname, kwargs[attrname])

        self._initializing.clear()

    def __eq__(self, other):
        if isinstance(other, Model):
            return other.data_key == self.data_key
        if isinstance(other, tuple):
            return other == self.data_key
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self, *field_names):
        if field_names:
            if self._pk_field not in field_names:
                field_names = (self._pk_field,) + field_names
        else:
            field_names = [k for k, v in iteritems(self._fields)
                           if k != self._pk_field and isinstance(v, Field)]
            field_names.sort()
            field_names.insert(0, self._pk_field)

        data_store = self.data_store
        fields = OrderedDict()
        for field_name in field_names:
            try:
                fields[field_name] = data_store.get(field_name)
            except KeyError:
                pass
        return u'{}<{}>({})'.format(
            self.__class__.__name__,
            self.snapshots[0],
            u', '.join(u'{}={!r}'.format(k, v) for k, v in iteritems(fields)))

    def __setattr__(self, key, value):
        if key not in self._own_attributes and key not in self._fields:
            raise TypeError(
                u"'{}' is not a field of model '{}'".format(
                    key, self.__class__.__name__))
        super(Model, self).__setattr__(key, value)

    def with_snapshots(self, snapshots=None):
        if self.snapshots == (snapshots or ModelSnapshots.default_snapshots):
            return self
        copy = self.__class__(self.storage, snapshots, _data_key=self.data_key)
        if copy.data_store is not self.data_store:
            copy.data_store.copy_from(self.data_store)
        return copy

    @property
    def pk(self):
        return getattr(self, self._pk_field)

    @cached_property
    def data_store(self):
        if self.storage:
            return self.shared_data_store.setdefault(
                self.storage, {}).setdefault(
                self.data_key, self.snapshot_class())
        return self.shared_data_store.setdefault(self, self.snapshot_class())

    def has_data(self, key):
        try:
            self.get_data(key)
        except AttributeError:
            return False
        return True

    def get_data(self, key, default=unspecified):
        self.resolve_attributes(key)
        try:
            return self.data_store.get(key, snapshots=self.snapshots)
        except KeyError:
            pass
        if default is not unspecified:
            return default
        raise AttributeError(
            u"'{}' object has no attribute '{}'".format(
                self.__class__.__name__, key))

    def set_data(self, key, value):
        self.data_store.set(key, value, snapshot=self.snapshots[0])

    def dump(self, state='working'):
        try:
            index = ModelSnapshots.default_snapshots.index(state)
        except ValueError:
            raise ValueError(u"'{}' is not a valid state".format(state))

        context = {
            'snapshots': ModelSnapshots.default_snapshots[index:]
        }
        return self.file_schema(strict=True, context=context).dump(self).data

    def dumps(self, state='working'):
        return json.dumps(self.dump(state=state), sort_keys=False, indent=4)

    def rollback(self):
        self.data_store.clear_snapshot('working')

    def save(self, only=None):
        if self.storage is None:
            return

        # make sure all attributes have been loaded before saving, we need them
        # to correctly detect path changes and to prevent data loss
        self.resolve_attributes(snapshots=('committed',))
        # stage changes to the selected fields in the model and across
        # relationships
        self._stage_changes(only)
        # now that all changes are staged we can save from the staged and
        # committed snapshots to get a consistent save of the selected fields
        self._commit_changes()

    def _stage_changes(self, only=None):
        store = self.data_store
        dirty = store.dirty_fields('working', ('committed',))
        if only is not None:
            dirty = dirty.intersection(only)
        if dirty:
            store.update_snapshot('staged', ('working',), fields=dirty)

        for model, field in self._staged_model_references():
            related_store = model.data_store
            related_field = model._fields[field]
            if related_field.only is None:
                related_dirty = dirty
            elif isinstance(related_field.only, string_types):
                related_dirty = dirty.intersection((related_field.only,))
            else:
                related_dirty = dirty.intersection(related_field.only)
            if related_dirty or field in related_store.dirty_fields(
                    'working', ('committed',)):
                related_store.update_snapshot(
                    'staged', ('working', 'committed'), fields=[field])

    def _commit_changes(self):
        saved_paths = set()
        deleted_paths = set()

        for model in chain([self], (model for model, _
                                    in self._staged_model_references())):
            store = model.data_store
            dirty = model._file_fields.intersection(iterkeys(store['staged']))
            path = model.storage_path(model, snapshots=('staged', 'committed'))
            old_path = model.storage_path(model,
                                          snapshots=('committed', 'staged'))
            if dirty or old_path != path:
                if path not in saved_paths:
                    if model.opts.owner:
                        child = model
                        while child.opts.owner:
                            parent_field = child.opts.owner
                            parent = getattr(
                                child.with_snapshots(('staged', 'committed')),
                                parent_field)
                            collection = getattr(
                                parent.with_snapshots(('staged', 'committed')),
                                child._fields[parent_field].related_name)
                            child = parent
                        model.storage.save(path, ContentFile(
                            collection.dumps(state='staged'), path))
                    else:
                        model.storage.save(path, ContentFile(
                            model.dumps(state='staged'), path))
                    saved_paths.add(path)
                if old_path != path and path not in deleted_paths:
                    model.storage.delete(old_path)
                    deleted_paths.add(old_path)

        for model in chain([self], (model for model, _
                                    in self._staged_model_references())):
            store = model.data_store
            dirty = set(iterkeys(store['staged']))
            if dirty:
                store.update_snapshot('committed', ('staged',), fields=dirty)
                store.clear_snapshot('staged')
                store.clear_snapshot('working', fields=dirty.intersection(
                    iterkeys(store['working'])))

    def _staged_model_references(self):
        for name, field in iteritems(self._fields):
            if isinstance(field, BaseRelationship):
                try:
                    value = self.data_store.get(name, ('staged', 'committed'))
                except KeyError:
                    continue
                if not isinstance(value, ModelCollection):
                    value = [value]
                for related in value:
                    related_name = field.related_name
                    yield related, related_name

    @classmethod
    def load(cls, storage, instance=None, **kwargs):
        if storage is None:
            return

        path = cls.storage_path(instance or kwargs,
                                snapshots=('committed', 'working'))
        if not path:
            return

        many = cls.opts.owner
        if instance and many:
            try:
                instance.data_store.get(instance._pk_field)
            except KeyError:
                return

        if path in cls.loaded.setdefault(storage, set()):
            return
        cls.loaded[storage].add(path)

        if not storage.exists(path):
            if many:
                return cls.collection()
            return instance  # may be None

        file_schema = cls._file_model.file_schema
        file_data = json.loads(storage.open(path).read(),
                               object_pairs_hook=OrderedDict)
        result = file_schema(strict=True, context={'storage': storage})\
            .load(file_data, many=many).data
        return result

    @classmethod
    def storage_path(cls, data, snapshots=None):
        if isinstance(data, cls):
            data = data.data_store.accessor(snapshots)
        else:
            data = AttributeDict(data)
        try:
            path = (cls.opts.path or u'').format(self=data)
        except AttributeError as e:
            raise PathResolutionError(
                u"Could not resolve file path for model '{}':\n"
                u"    {}".format(cls.__name__, e))
        return path or None

    def resolve_attributes(self, *attributes, **kwargs):
        if not self.storage:
            return

        file_fields = self._file_fields
        if not attributes:
            attributes = file_fields

        snapshots = kwargs.get('snapshots')
        if snapshots is None:
            snapshots = self.snapshots
        data = self.data_store.accessor(snapshots)
        try:
            for attribute in attributes:
                if (attribute in file_fields and
                        attribute not in self._initializing and
                        not hasattr(data, attribute)):
                    self.load(self.storage, instance=self)
                    break
        except PathResolutionError:
            pass
