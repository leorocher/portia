from slyd.orm import fields
from slyd.orm.base import Model


class ExampleModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Boolean()


class RequiredFieldModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field(required=True)


class SingleFileModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()

    class Meta:
        path = u'single.json'


class ManyFileModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    owner = fields.BelongsTo('ManyFileModel', related_name='owner',
                             ignore_in_file=True)

    class Meta:
        path = u'many.json'
        owner = 'owner'


class ParamFileModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    param = fields.String()

    class Meta:
        path = u'param-{self.param}.json'


class EnvelopeModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()

    class Meta:
        path = u'envelope.json'
        envelope = True


class OneToOneModel1(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    m2 = fields.BelongsTo('OneToOneModel2', related_name='m1', only='id')

    class Meta:
        path = u'o2o-model-1.json'


class OneToOneModel2(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    m1 = fields.BelongsTo(OneToOneModel1, related_name='m2')

    class Meta:
        path = u'o2o-model-2.json'


class ChildModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    parent = fields.BelongsTo('ParentModel', related_name='children', only='id')

    class Meta:
        path = u'{self.parent.id}/children.json'
        owner = 'parent'


class ParentModel(Model):
    id = fields.String(primary_key=True)
    field = fields.Field()
    children = fields.HasMany(ChildModel, related_name='parent')

    class Meta:
        path = u'parents.json'
