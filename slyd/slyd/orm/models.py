from collections import OrderedDict

from six import iteritems

from slybot.fieldtypes import FieldTypeManager
from slyd.orm.base import Model
from slyd.orm.decorators import pre_load, post_dump
from slyd.orm.fields import (Boolean, Domain, List, Regexp, String, Url,
                             DependantField, BelongsTo, HasMany)
from slyd.orm.validators import OneOf

FIELD_TYPES = FieldTypeManager().available_type_names()


class Project(Model):
    # TODO: override storage for hosted version, return generated project.json
    name = String(primary_key=True)
    spiders = HasMany('Spider', related_name='project', ignore_in_file=True)
    schemas = HasMany('Schema', related_name='project', ignore_in_file=True)
    extractors = HasMany('Extractor', related_name='project',
                         ignore_in_file=True)

    class Meta:
        path = u'project.json'


class Schema(Model):
    id = String(primary_key=True)
    name = String(required=True)
    project = BelongsTo(Project, related_name='schemas', ignore_in_file=True)
    fields = HasMany('Field', related_name='schema')
    # TODO: link into sample items
    # items = HasMany('Item', related_name='schema', ignore_in_file=True)

    class Meta:
        path = u'items.json'
        owner = 'project'
        envelope = True
        envelope_remove_key = True

    @pre_load
    def name_from_id(self, data):
        if 'name' not in data:
            # display_name ?
            data['name'] = data['id']
        return data


class Field(Model):
    id = String(primary_key=True)
    name = String(required=True)
    type = String(required=True, default='text', validate=OneOf(FIELD_TYPES))
    required = Boolean(default=False)
    vary = Boolean(default=False)
    schema = BelongsTo(Schema, related_name='fields', ignore_in_file=True)
    # TODO: link into sample annotations
    # annotations = HasMany('Annotation', related_name='field',
    #                       ignore_in_file=True)

    class Meta:
        path = u'items.json'
        owner = 'schema'
        envelope = True

    def __repr__(self):
        return super(Field, self).__repr__('name', 'type')


class Extractor(Model):
    id = String(primary_key=True)
    type = String(required=True, validate=OneOf(['type', 'regex']))
    value = DependantField(when='type', then={
        'type': String(required=True, validate=OneOf(FIELD_TYPES)),
        'regex': Regexp(required=True),
    })
    project = BelongsTo(Project, related_name='extractors',
                        ignore_in_file=True)
    # TODO: link into sample annotations
    # annotations = HasMany('Annotation', related_name='extractors',
    #                       ignore_in_file=True)

    class Meta:
        path = u'extractors.json'
        owner = 'project'
        envelope = True

    @pre_load
    def to_type_and_value(self, data):
        type_extractor = data.pop('type_extractor', None)
        regular_expression = data.pop('regular_expression', None)
        if type_extractor:
            data['type'] = 'type'
            data['value'] = type_extractor
        elif regular_expression:
            data['type'] = 'regex'
            data['value'] = regular_expression
        return data

    @post_dump
    def from_type_and_value(self, data):
        type_ = data.pop('type')
        value = data.pop('value')
        if type_ == 'type':
            data['type_extractor'] = value
        else:  # type_ == 'regex'
            data['regular_expression'] = value
        return data


class Spider(Model):
    id = String(primary_key=True)
    start_urls = List(Url)
    # TODO: generated urls
    links_to_follow = String(default="all", validate=OneOf(
        ["none", "patterns", "all", "auto"]))
    # TODO: compute automatically from start urls
    allowed_domains = List(Domain)
    respect_nofollow = Boolean(default=True)
    follow_patterns = List(Regexp)
    exclude_patterns = List(Regexp)
    js_enabled = Boolean(default=False)
    js_enable_patterns = List(Regexp)
    js_disable_patterns = List(Regexp)
    perform_login = Boolean(default=False)
    login_url = String(default='')
    login_user = String(default='')
    login_password = String(default='')
    project = BelongsTo(Project, related_name='spiders', ignore_in_file=True)
    samples = HasMany('Sample', related_name='spider', only='id',
                      load_from='template_names', dump_to='template_names')

    class Meta:
        path = u'spiders/{self.id}.json'

    def __repr__(self):
        return super(Spider, self).__repr__('id')

    @classmethod
    def load(cls, storage, instance=None, project=None, **kwargs):
        if instance is None and project:
            # Load Spiders collection from file listing
            directories, files = storage.listdir('spiders')
            return cls.collection(
                cls(storage, snapshots=('committed',),
                    id=filename[:-len('.json')]).with_snapshots()
                for filename in files
                if filename.endswith('.json'))

        return super(Spider, cls).load(
            storage, instance, project=project, **kwargs)

    @pre_load
    def get_init_requests(self, data):
        init_requests = data.pop('init_requests', [])
        if init_requests:
            login_request = init_requests[0]
            if isinstance(login_request, dict):
                data['login_url'] = login_request.get('loginurl', '')
                data['login_user'] = login_request.get('username', '')
                data['login_password'] = login_request.get('password', '')
        data['perform_login'] = self._is_perform_login(data)
        return data

    @post_dump
    def set_init_requests(self, data):
        if data.pop('perform_login', None) and self._is_perform_login(data):
            data['init_requests'] = [OrderedDict([
                ('type', 'login'),
                ('loginurl', data['login_url']),
                ('username', data['login_user']),
                ('password', data['login_password']),
            ])]
        data.pop('login_url', None)
        data.pop('login_user', None)
        data.pop('login_password', None)
        return OrderedDict(sorted(iteritems(data)))

    @staticmethod
    def _is_perform_login(data):
        return all(data.get(field)
                   for field in ('login_url', 'login_user', 'login_password'))


class Sample(Model):
    id = String(primary_key=True)
    name = String(required=True)
    url = Url(required=True)
    spider = BelongsTo(Spider, related_name='samples', only='id')

    class Meta:
        path = u'spiders/{self.spider.id}/{self.id}.json'

    def __repr__(self):
        return super(Sample, self).__repr__('name', 'url')

    @classmethod
    def load(cls, storage, instance=None, spider=None, **kwargs):
        if instance is None and spider:
            # Samples are stored in separate files, but they are listed in the
            # Spider file. If this gets called, it means that file didn't exist
            # so return an empty collection
            return cls.collection()

        return super(Sample, cls).load(
            storage, instance, spider=spider, **kwargs)


def init_storage():
    from slyd_dash import settings
    from slyd.gitstorage import repo
    from slyd.utils.storage import GitStorage
    from slyd.gitstorage.repoman import Repoman

    rs = dict(settings.SPEC_FACTORY.get('PARAMS'))
    del rs['dash_url']
    Repoman.setup(**rs)
    repo.set_db_url(rs['location'])
    connection = repo.connection_pool.connectionFactory(repo.connection_pool)

    repo = Repoman.open_repo('2222238', connection, author='michal <>')
    storage = GitStorage(repo, branch='staff')
    return storage


if __name__ == '__main__':
    storage = init_storage()

    # print storage.open('items.json').read()
    # print storage.open('extractors.json').read()
    # print storage.listdir('spiders')
    # print storage.listdir('spiders/owlkingdom.com')
    # print storage.open('spiders/owlkingdom.com.json').read()
    # print storage.open('spiders/owlkingdom.com/1ddc-4043-ac4d.json').read()
    # print

    # import sys
    # sys.setrecursionlimit(100)

    project = Project(storage, name='2222238')
    print project
    print

    # print project.schemas
    # print

    print project.schemas['5118-4990-9ee0'].fields['02bc-4d7f-bd53']
    print

    print project.extractors['e6fc-4758-9e6b']
    print

    spider = Spider(storage, id='owlkingdom.com')
    print spider
    # print spider.samples
    # print spider.samples['1ddc-4043-ac4d']
    # print spider.dumps()
    print

    sample = Sample(storage, id='1ddc-4043-ac4d', spider=spider)
    print sample
    print sample.dumps()
    print spider.samples
    print spider.samples['1ddc-4043-ac4d']
    print spider.dumps()
    print

    # # partial_spider = Spider(storage, id='owlkingdom.com')
    # partial_sample = Sample(storage, id='1ddc-4043-ac4d', spider=spider)
    # print partial_sample
    # print partial_sample.dumps()
    # print

    # print partial_spider
    # print partial_spider.dumps()
    # print
