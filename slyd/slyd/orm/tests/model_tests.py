import unittest

import mock

from slyd.orm.exceptions import ValidationError
from slyd.orm.models import Project, Schema, Field, Extractor, Spider, Sample
from .utils import mock_storage


class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self.storage = mock_storage({
            'project.json':
                '{'
                '    "name": "example"'
                '}',
            'items.json':
                '{'
                '    "1664-4f20-b657": {'
                '        "fields": {'
                '            "fbec-4a42-a4b0": {'
                '                "id": "fbec-4a42-a4b0",'
                '                "name": "title",'
                '                "required": true,'
                '                "type": "text",'
                '                "vary": false'
                '            },'
                '            "cca5-490c-b604": {'
                '                "id": "cca5-490c-b604",'
                '                "name": "price",'
                '                "required": true,'
                '                "type": "price",'
                '                "vary": false'
                '            },'
                '            "34bc-406f-80bc": {'
                '                "id": "34bc-406f-80bc",'
                '                "name": "image",'
                '                "required": false,'
                '                "type": "image",'
                '                "vary": false'
                '            },'
                '            "ecfc-4dbe-b488": {'
                '                "id": "ecfc-4dbe-b488",'
                '                "name": "details",'
                '                "required": false,'
                '                "type": "text",'
                '                "vary": false'
                '            }'
                '        },'
                '        "name": "product"'
                '    },'
                '    "fa87-4791-8642": {'
                '        "fields": {},'
                '        "name": "other"'
                '    }'
                '}',
            'extractors.json':
                '{'
                '    "e6fc-4758-9e6b": {'
                '        "id": "e6fc-4758-9e6b",'
                '        "regular_expression": "\\\\$(\\\\d+(?:\\\\.\\\\d{2}))"'
                '    },'
                '    "154f-45ce-bfbd": {'
                '        "id": "154f-45ce-bfbd",'
                '        "type_extractor": "number"'
                '    }'
                '}',
            'spiders/shop-crawler.json':
                '{'
                '    "allowed_domains": [],'
                '    "exclude_patterns": [],'
                '    "follow_patterns": [],'
                '    "id": "shop-crawler",'
                '    "init_requests": ['
                '        {'
                '            "type": "login",'
                '            "loginurl": "http://shop.example.com/login",'
                '            "username": "user",'
                '            "password": "pass"'
                '        }'
                '    ],'
                '    "js_disable_patterns": [],'
                '    "js_enable_patterns": [],'
                '    "js_enabled": false,'
                '    "links_to_follow": "all",'
                '    "name": "shop-crawler",'
                '    "project": "example",'
                '    "respect_nofollow": true,'
                '    "start_urls": ['
                '        "http://owlkingdom.com/"'
                '    ],'
                '    "template_names": ['
                '        "1ddc-4043-ac4d"'
                '    ]'
                '}',
            'spiders/shop-crawler/1ddc-4043-ac4d.json':
                '{'
                '    "id": "1ddc-4043-ac4d",'
                '    "name": "example",'
                '    "url": "http://example.com",'
                '    "spider": "shop-crawler"'
                '}'
        })


class ProjectTests(ProjectTestCase):
    def test_project(self):
        project = Project(name='project-1')
        self.assertEqual(project.dump(), {
            'name': 'project-1',
        })

    def test_load(self):
        project = Project(self.storage, name='example')
        self.assertEqual(project.dump(), {
            'name': 'example',
        })
        self.storage.open.assert_not_called()

    def test_save(self):
        project = Project(self.storage, name='example')
        project.save()

        self.storage.open.assert_called_once_with('project.json')
        self.storage.save.assert_not_called()

        project.name = 'test'
        project.save()

        self.storage.open.assert_called_once_with('project.json')
        self.storage.save.assert_called_once_with('project.json', mock.ANY)
        self.assertEqual(
            self.storage.files['project.json'],
            '{\n'
            '    "name": "test"\n'
            '}')


class SchemaTests(ProjectTestCase):
    def test_no_fields(self):
        schema = Schema(id='schema-1', name='default')

        self.assertEqual(len(schema.fields), 0)
        self.assertEqual(schema.dump(), {
            'schema-1': {
                'name': 'default',
                'fields': {},
            },
        })

    def test_fields(self):
        schema = Schema(id='schema-1', name='default')
        Field(id='field-1', name='name', schema=schema)
        Field(id='field-2', name='url', type='url', schema=schema)

        self.assertEqual(schema.dump(), {
            'schema-1': {
                'name': 'default',
                'fields': {
                    'field-1': {
                        'id': 'field-1',
                        'name': 'name',
                        'type': 'text',
                        'required': False,
                        'vary': False,
                    },
                    'field-2': {
                        'id': 'field-2',
                        'name': 'url',
                        'type': 'url',
                        'required': False,
                        'vary': False,
                    },
                },
            },
        })

    def test_collection(self):
        schemas = Schema.collection([
            Schema(id='schema-1', name='default', fields=[
                Field(id='field-1', name='name'),
            ]),
            Schema(id='schema-2', name='other', fields=[
                Field(id='field-2', name='xxx'),
            ]),
        ])

        self.assertEqual(schemas.dump(), {
            'schema-1': {
                'name': 'default',
                'fields': {
                    'field-1': {
                        'id': 'field-1',
                        'name': 'name',
                        'type': 'text',
                        'required': False,
                        'vary': False,
                    },
                },
            },
            'schema-2': {
                'name': 'other',
                'fields': {
                    'field-2': {
                        'id': 'field-2',
                        'name': 'xxx',
                        'type': 'text',
                        'required': False,
                        'vary': False,
                    },
                },
            },
        })

    def test_load_through_project(self):
        project = Project(self.storage, name='example')
        schemas = project.schemas

        self.storage.open.assert_called_once_with('items.json')
        self.assertIsInstance(schemas, Schema.collection)
        self.assertEqual(schemas.dump(), {
            '1664-4f20-b657': {
                'name': 'product',
                'fields': {
                    'fbec-4a42-a4b0': {
                        'id': 'fbec-4a42-a4b0',
                        'name': 'title',
                        'type': 'text',
                        'required': True,
                        'vary': False,
                    },
                    "cca5-490c-b604": {
                        "id": "cca5-490c-b604",
                        "name": "price",
                        "required": True,
                        "type": "price",
                        "vary": False
                    },
                    "34bc-406f-80bc": {
                        "id": "34bc-406f-80bc",
                        "name": "image",
                        "required": False,
                        "type": "image",
                        "vary": False
                    },
                    "ecfc-4dbe-b488": {
                        "id": "ecfc-4dbe-b488",
                        "name": "details",
                        "required": False,
                        "type": "text",
                        "vary": False
                    }
                },
            },
            'fa87-4791-8642': {
                'name': 'other',
                'fields': {},
            },
        })
        self.assertListEqual(schemas.keys(),
                             ['1664-4f20-b657', 'fa87-4791-8642'])

    def test_load_through_partial(self):
        schema = Schema(self.storage, id='1664-4f20-b657')
        self.storage.open.assert_not_called()
        self.assertEqual(schema.dump(), {
            '1664-4f20-b657': {
                'name': 'product',
                'fields': {
                    'fbec-4a42-a4b0': {
                        'id': 'fbec-4a42-a4b0',
                        'name': 'title',
                        'type': 'text',
                        'required': True,
                        'vary': False,
                    },
                    "cca5-490c-b604": {
                        "id": "cca5-490c-b604",
                        "name": "price",
                        "required": True,
                        "type": "price",
                        "vary": False
                    },
                    "34bc-406f-80bc": {
                        "id": "34bc-406f-80bc",
                        "name": "image",
                        "required": False,
                        "type": "image",
                        "vary": False
                    },
                    "ecfc-4dbe-b488": {
                        "id": "ecfc-4dbe-b488",
                        "name": "details",
                        "required": False,
                        "type": "text",
                        "vary": False
                    }
                },
            },
        })
        self.storage.open.assert_called_once_with('items.json')

    def test_save_edit(self):
        schema = Project(self.storage, name='example').schemas['1664-4f20-b657']
        schema.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_not_called()

        schema.name = 'test'
        schema.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_called_once_with('items.json', mock.ANY)
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "test"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')

        schema.id = 'xxxx-xxxx-xxxx'
        schema.save()

        self.storage.open.assert_called_once_with('items.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('items.json', mock.ANY),
            mock.call('items.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "test"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')

    def test_save_new(self):
        project = Project(self.storage, name='example')
        schema = Schema(self.storage, id='xxxx-xxxx-xxxx', name='test1',
                        project=project)
        schema.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_called_once_with('items.json', mock.ANY)
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }, \n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "fields": {}, \n'
            '        "name": "test1"\n'
            '    }\n'
            '}')

        project.schemas.insert(
            0, Schema(self.storage, id='yyyy-yyyy-yyyy', name='test2'))
        project.schemas[0].save()

        self.storage.open.assert_called_once_with('items.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('items.json', mock.ANY),
            mock.call('items.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "yyyy-yyyy-yyyy": {\n'
            '        "fields": {}, \n'
            '        "name": "test2"\n'
            '    }, \n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }, \n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "fields": {}, \n'
            '        "name": "test1"\n'
            '    }\n'
            '}')


class FieldTests(ProjectTestCase):
    def test_minimal_field(self):
        field = Field(id='field-1', name='url')

        self.assertEqual(field.dump(), {
            'field-1': {
                'id': 'field-1',
                'name': 'url',
                'type': 'text',
                'required': False,
                'vary': False,
            },
        })

    def test_full_field(self):
        field = Field(id='field-1', name='url', type='url',
                      required=True, vary=True)

        self.assertEqual(field.dump(), {
            'field-1': {
                'id': 'field-1',
                'name': 'url',
                'type': 'url',
                'required': True,
                'vary': True,
            },
        })

    def test_field_types(self):
        field = Field(id='field-1', name='url')

        try:
            field.type = 'image'
            field.type = 'number'
            field.type = 'url'
        except ValidationError:
            self.fail(
                "Assigning to type attribute failed validation")

        with self.assertRaises(ValidationError):
            field.type = 'xxx'

    def test_load_through_project(self):
        project = Project(self.storage, name='example')
        fields = project.schemas['1664-4f20-b657'].fields

        self.storage.open.assert_called_once_with('items.json')
        self.assertIsInstance(fields, Field.collection)
        self.assertEqual(fields.dump(), {
            'fbec-4a42-a4b0': {
                'id': 'fbec-4a42-a4b0',
                'name': 'title',
                'type': 'text',
                'required': True,
                'vary': False,
            },
            "cca5-490c-b604": {
                "id": "cca5-490c-b604",
                "name": "price",
                "required": True,
                "type": "price",
                "vary": False
            },
            "34bc-406f-80bc": {
                "id": "34bc-406f-80bc",
                "name": "image",
                "required": False,
                "type": "image",
                "vary": False
            },
            "ecfc-4dbe-b488": {
                "id": "ecfc-4dbe-b488",
                "name": "details",
                "required": False,
                "type": "text",
                "vary": False
            },
        })
        self.assertListEqual(fields.keys(),
                             ['fbec-4a42-a4b0', "cca5-490c-b604",
                              "34bc-406f-80bc", "ecfc-4dbe-b488"])

    def test_load_through_partial(self):
        field = Field(self.storage, id='ecfc-4dbe-b488')
        self.assertEqual(field.dump(), {
            "ecfc-4dbe-b488": {
                "id": "ecfc-4dbe-b488",
                "name": "details",
                "required": False,
                "type": "text",
                "vary": False
            },
        })
        self.storage.open.assert_called_once_with('items.json')

    def test_save_edit(self):
        field = Project(self.storage, name='example').schemas['1664-4f20-b657']\
                                                     .fields['fbec-4a42-a4b0']
        field.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_not_called()

        field.name = 'test'
        field.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_called_once_with('items.json', mock.ANY)
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "test", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')

        field.id = 'xxxx-xxxx-xxxx'
        field.save()

        self.storage.open.assert_called_once_with('items.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('items.json', mock.ANY),
            mock.call('items.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "xxxx-xxxx-xxxx": {\n'
            '                "id": "xxxx-xxxx-xxxx", \n'
            '                "name": "test", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')

    def test_save_new(self):
        schema = Project(self.storage, name='example').schemas['1664-4f20-b657']
        field = Field(self.storage, id='xxxx-xxxx-xxxx', name='test1',
                      schema=schema)
        field.save()

        self.storage.open.assert_called_once_with('items.json')
        self.storage.save.assert_called_once_with('items.json', mock.ANY)
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "xxxx-xxxx-xxxx": {\n'
            '                "id": "xxxx-xxxx-xxxx", \n'
            '                "name": "test1", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')

        schema.fields.insert(
            0, Field(self.storage, id='yyyy-yyyy-yyyy', name='test2'))
        schema.fields[0].save()

        self.storage.open.assert_called_once_with('items.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('items.json', mock.ANY),
            mock.call('items.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['items.json'],
            '{\n'
            '    "1664-4f20-b657": {\n'
            '        "fields": {\n'
            '            "yyyy-yyyy-yyyy": {\n'
            '                "id": "yyyy-yyyy-yyyy", \n'
            '                "name": "test2", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "fbec-4a42-a4b0": {\n'
            '                "id": "fbec-4a42-a4b0", \n'
            '                "name": "title", \n'
            '                "required": true, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "cca5-490c-b604": {\n'
            '                "id": "cca5-490c-b604", \n'
            '                "name": "price", \n'
            '                "required": true, \n'
            '                "type": "price", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "34bc-406f-80bc": {\n'
            '                "id": "34bc-406f-80bc", \n'
            '                "name": "image", \n'
            '                "required": false, \n'
            '                "type": "image", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "ecfc-4dbe-b488": {\n'
            '                "id": "ecfc-4dbe-b488", \n'
            '                "name": "details", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }, \n'
            '            "xxxx-xxxx-xxxx": {\n'
            '                "id": "xxxx-xxxx-xxxx", \n'
            '                "name": "test1", \n'
            '                "required": false, \n'
            '                "type": "text", \n'
            '                "vary": false\n'
            '            }\n'
            '        }, \n'
            '        "name": "product"\n'
            '    }, \n'
            '    "fa87-4791-8642": {\n'
            '        "fields": {}, \n'
            '        "name": "other"\n'
            '    }\n'
            '}')


class ExtractorTests(ProjectTestCase):
    def test_type_extractor(self):
        extractor = Extractor(id='extractor-1', type='type', value='url')

        self.assertEqual(extractor.dump(), {
            'extractor-1': {
                'id': 'extractor-1',
                'type_extractor': 'url',
            },
        })

        try:
            extractor.value = 'image'
            extractor.value = 'number'
            extractor.value = 'text'
        except ValidationError:
            self.fail(
                "Assigning to value attribute failed validation")

        with self.assertRaises(ValidationError):
            extractor.value = 'xxx'

    def test_regexp_extractor(self):
        extractor = Extractor(id='extractor-1', type='regex', value='(.+)')

        self.assertEqual(extractor.dump(), {
            'extractor-1': {
                'id': 'extractor-1',
                'regular_expression': '(.+)',
            },
        })

        try:
            extractor.value = '[xy]'
        except ValidationError:
            self.fail(
                "Assigning to value attribute failed validation")

        with self.assertRaises(ValidationError):
            extractor.value = '[xy'

        self.assertEqual(extractor.dump(), {
            'extractor-1': {
                'id': 'extractor-1',
                'regular_expression': '[xy]',
            },
        })

    def test_extractor_type(self):
        extractor = Extractor(id='extractor-1', type='type', value='text')
        try:
            extractor.type = 'regex'
            extractor.type = 'type'
        except ValidationError:
            self.fail(
                "Assigning to type attribute failed validation")

        with self.assertRaises(ValidationError):
            extractor.type = 'xxx'

    def test_collection(self):
        extractors = Extractor.collection([
            Extractor(id='extractor-1', type='type', value='url'),
            Extractor(id='extractor-2', type='regex', value='(.+)'),
        ])

        self.assertEqual(extractors.dump(), {
            'extractor-1': {
                'id': 'extractor-1',
                'type_extractor': 'url',
            },
            'extractor-2': {
                'id': 'extractor-2',
                'regular_expression': '(.+)',
            },
        })

    def test_load_through_project(self):
        project = Project(self.storage, name='example')
        extractors = project.extractors

        self.storage.open.assert_called_once_with('extractors.json')
        self.assertIsInstance(extractors, Extractor.collection)
        self.assertEqual(extractors.dump(), {
            "e6fc-4758-9e6b": {
                "id": "e6fc-4758-9e6b",
                "regular_expression": "\\$(\\d+(?:\\.\\d{2}))",
            },
            "154f-45ce-bfbd": {
                "id": "154f-45ce-bfbd",
                "type_extractor": "number",
            },
        })
        self.assertListEqual(extractors.keys(),
                             ['e6fc-4758-9e6b', "154f-45ce-bfbd"])

    def test_load_through_partial(self):
        extractor = Extractor(self.storage, id='e6fc-4758-9e6b')
        self.assertEqual(extractor.dump(), {
            "e6fc-4758-9e6b": {
                "id": "e6fc-4758-9e6b",
                "regular_expression": "\\$(\\d+(?:\\.\\d{2}))",
            },
        })
        self.storage.open.assert_called_once_with('extractors.json')

    def test_save_edit(self):
        extractor = Project(
            self.storage, name='example').extractors['e6fc-4758-9e6b']
        extractor.save()

        self.storage.open.assert_called_once_with('extractors.json')
        self.storage.save.assert_not_called()

        extractor.value = 'test'
        extractor.save()

        self.storage.open.assert_called_once_with('extractors.json')
        self.storage.save.assert_called_once_with('extractors.json', mock.ANY)
        self.assertEqual(
            self.storage.files['extractors.json'],
            '{\n'
            '    "e6fc-4758-9e6b": {\n'
            '        "id": "e6fc-4758-9e6b", \n'
            '        "regular_expression": "test"\n'
            '    }, \n'
            '    "154f-45ce-bfbd": {\n'
            '        "id": "154f-45ce-bfbd", \n'
            '        "type_extractor": "number"\n'
            '    }\n'
            '}')

        extractor.id = 'xxxx-xxxx-xxxx'
        extractor.save()

        self.storage.open.assert_called_once_with('extractors.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('extractors.json', mock.ANY),
            mock.call('extractors.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['extractors.json'],
            '{\n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "id": "xxxx-xxxx-xxxx", \n'
            '        "regular_expression": "test"\n'
            '    }, \n'
            '    "154f-45ce-bfbd": {\n'
            '        "id": "154f-45ce-bfbd", \n'
            '        "type_extractor": "number"\n'
            '    }\n'
            '}')

    def test_save_new(self):
        project = Project(self.storage, name='example')
        extractor = Extractor(self.storage, id='xxxx-xxxx-xxxx',
                              type='regex', value='test1',
                              project=project)
        extractor.save()

        self.storage.open.assert_called_once_with('extractors.json')
        self.storage.save.assert_called_once_with('extractors.json', mock.ANY)
        self.assertEqual(
            self.storage.files['extractors.json'],
            '{\n'
            '    "e6fc-4758-9e6b": {\n'
            '        "id": "e6fc-4758-9e6b", \n'
            '        "regular_expression": "\\\\$(\\\\d+(?:\\\\.\\\\d{2}))"\n'
            '    }, \n'
            '    "154f-45ce-bfbd": {\n'
            '        "id": "154f-45ce-bfbd", \n'
            '        "type_extractor": "number"\n'
            '    }, \n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "id": "xxxx-xxxx-xxxx", \n'
            '        "regular_expression": "test1"\n'
            '    }\n'
            '}')

        project.extractors.insert(
            0, Extractor(self.storage, id='yyyy-yyyy-yyyy',
                         type='regex', value='test2'))
        project.extractors[0].save()

        self.storage.open.assert_called_once_with('extractors.json')
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('extractors.json', mock.ANY),
            mock.call('extractors.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['extractors.json'],
            '{\n'
            '    "yyyy-yyyy-yyyy": {\n'
            '        "id": "yyyy-yyyy-yyyy", \n'
            '        "regular_expression": "test2"\n'
            '    }, \n'
            '    "e6fc-4758-9e6b": {\n'
            '        "id": "e6fc-4758-9e6b", \n'
            '        "regular_expression": "\\\\$(\\\\d+(?:\\\\.\\\\d{2}))"\n'
            '    }, \n'
            '    "154f-45ce-bfbd": {\n'
            '        "id": "154f-45ce-bfbd", \n'
            '        "type_extractor": "number"\n'
            '    }, \n'
            '    "xxxx-xxxx-xxxx": {\n'
            '        "id": "xxxx-xxxx-xxxx", \n'
            '        "regular_expression": "test1"\n'
            '    }\n'
            '}')


class SpiderTests(ProjectTestCase):
    def test_minimal_spider(self):
        spider = Spider(id='spider-1')
        spider.start_urls.append('http://example.com')

        self.assertEqual(spider.dump(), {
            'id': 'spider-1',
            'start_urls': [
                'http://example.com',
            ],
            'links_to_follow': "all",
            'allowed_domains': [],
            'respect_nofollow': True,
            'follow_patterns': [],
            'exclude_patterns': [],
            'js_enabled': False,
            'js_enable_patterns': [],
            'js_disable_patterns': [],
            'template_names': [],
        })

    def test_full_spider(self):
        spider = Spider(
            id='spider-1',
            start_urls=['http://example.com'],
            links_to_follow="none",
            allowed_domains=['example.com'],
            respect_nofollow=False,
            follow_patterns=['.*'],
            exclude_patterns=['.*ignore.*'],
            js_enabled=True,
            js_enable_patterns=['.*'],
            js_disable_patterns=['.*ignore.*'],
            perform_login=True,
            login_url='http://shop.example.com/login',
            login_user='user',
            login_password='pass',
            samples=[
                Sample(id='sample-1'),
            ],
        )

        self.assertEqual(spider.dump(), {
            'id': 'spider-1',
            'start_urls': [
                'http://example.com',
            ],
            'links_to_follow': "none",
            'allowed_domains': [
                'example.com',
            ],
            'respect_nofollow': False,
            'follow_patterns': [
                '.*',
            ],
            'exclude_patterns': [
                '.*ignore.*',
            ],
            'js_enabled': True,
            'js_enable_patterns': [
                '.*',
            ],
            'js_disable_patterns': [
                '.*ignore.*',
            ],
            'init_requests': [
                {
                    'type': 'login',
                    'loginurl': 'http://shop.example.com/login',
                    'username': 'user',
                    'password': 'pass'
                }
            ],
            'template_names': [
                'sample-1',
            ],
        })

    def test_links_to_follow(self):
        spider = Spider(id='spider-1')

        try:
            spider.links_to_follow = 'patterns'
            spider.links_to_follow = 'auto'
            spider.links_to_follow = 'none'
            spider.links_to_follow = 'all'
        except ValidationError:
            self.fail(
                "Assigning to type attribute failed validation")

        with self.assertRaises(ValidationError):
            spider.links_to_follow = 'xxx'

    def test_load_through_project(self):
        project = Project(self.storage, name='example')
        spiders = project.spiders
        self.assertListEqual(spiders.keys(), ['shop-crawler'])
        self.assertIsInstance(spiders, Spider.collection)
        self.storage.open.assert_not_called()
        self.storage.listdir.assert_called_once_with('spiders')
        self.assertEqual(spiders.dump(), [
            {
                "id": "shop-crawler",
                # "name": "shop-crawler",
                "start_urls": [
                    "http://owlkingdom.com/"
                ],
                "links_to_follow": "all",
                "allowed_domains": [],
                "respect_nofollow": True,
                "follow_patterns": [],
                "exclude_patterns": [],
                "js_enabled": False,
                "js_enable_patterns": [],
                "js_disable_patterns": [],
                "init_requests": [
                    {
                        "type": "login",
                        "loginurl": "http://shop.example.com/login",
                        "username": "user",
                        "password": "pass"
                    }
                ],
                "template_names": [
                    "1ddc-4043-ac4d"
                ]
            },
        ])
        self.storage.open.assert_called_once_with('spiders/shop-crawler.json')

    def test_load_through_partial(self):
        spider = Spider(self.storage, id='shop-crawler')
        self.assertEqual(spider.dump(), {
            "id": "shop-crawler",
            # "name": "shop-crawler",
            "start_urls": [
                "http://owlkingdom.com/"
            ],
            "links_to_follow": "all",
            "allowed_domains": [],
            "respect_nofollow": True,
            "follow_patterns": [],
            "exclude_patterns": [],
            "js_enabled": False,
            "js_enable_patterns": [],
            "js_disable_patterns": [],
            "init_requests": [
                {
                    "type": "login",
                    "loginurl": "http://shop.example.com/login",
                    "username": "user",
                    "password": "pass"
                }
            ],
            "template_names": [
                "1ddc-4043-ac4d"
            ]
        })
        self.storage.open.assert_called_once_with('spiders/shop-crawler.json')

    def test_save_edit(self):
        spider = Project(self.storage, name='example').spiders['shop-crawler']
        spider.save()

        self.storage.open.assert_called_once_with('spiders/shop-crawler.json')
        self.storage.save.assert_not_called()

        spider.follow_patterns.append('test')
        spider.save()

        self.storage.open.assert_called_once_with('spiders/shop-crawler.json')
        self.storage.save.assert_called_once_with(
            'spiders/shop-crawler.json', mock.ANY)
        self.assertEqual(
            self.storage.files['spiders/shop-crawler.json'],
            '{\n'
            '    "allowed_domains": [], \n'
            '    "exclude_patterns": [], \n'
            '    "follow_patterns": [\n'
            '        "test"\n'
            '    ], \n'
            '    "id": "shop-crawler", \n'
            '    "init_requests": [\n'
            '        {\n'
            '            "type": "login", \n'
            '            "loginurl": "http://shop.example.com/login", \n'
            '            "username": "user", \n'
            '            "password": "pass"\n'
            '        }\n'
            '    ], \n'
            '    "js_disable_patterns": [], \n'
            '    "js_enable_patterns": [], \n'
            '    "js_enabled": false, \n'
            '    "links_to_follow": "all", \n'
            '    "respect_nofollow": true, \n'
            '    "start_urls": [\n'
            '        "http://owlkingdom.com/"\n'
            '    ], \n'
            '    "template_names": [\n'
            '        "1ddc-4043-ac4d"\n'
            '    ]\n'
            '}')

        spider.id = 'test-id'
        spider.save()

        self.assertEqual(self.storage.open.call_count, 2)
        self.storage.open.assert_has_calls([
            mock.call('spiders/shop-crawler.json'),
            mock.call('spiders/shop-crawler/1ddc-4043-ac4d.json')])
        self.assertEqual(self.storage.save.call_count, 3)
        self.storage.save.assert_has_calls([
            mock.call('spiders/shop-crawler.json', mock.ANY),
            mock.call('spiders/test-id.json', mock.ANY),
            mock.call('spiders/test-id/1ddc-4043-ac4d.json', mock.ANY)])
        self.assertEqual(self.storage.open.call_count, 2)
        self.storage.open.assert_has_calls([
            mock.call('spiders/shop-crawler.json'),
            mock.call('spiders/shop-crawler/1ddc-4043-ac4d.json')])
        self.assertEqual(
            self.storage.files['spiders/test-id.json'],
            '{\n'
            '    "allowed_domains": [], \n'
            '    "exclude_patterns": [], \n'
            '    "follow_patterns": [\n'
            '        "test"\n'
            '    ], \n'
            '    "id": "test-id", \n'
            '    "init_requests": [\n'
            '        {\n'
            '            "type": "login", \n'
            '            "loginurl": "http://shop.example.com/login", \n'
            '            "username": "user", \n'
            '            "password": "pass"\n'
            '        }\n'
            '    ], \n'
            '    "js_disable_patterns": [], \n'
            '    "js_enable_patterns": [], \n'
            '    "js_enabled": false, \n'
            '    "links_to_follow": "all", \n'
            '    "respect_nofollow": true, \n'
            '    "start_urls": [\n'
            '        "http://owlkingdom.com/"\n'
            '    ], \n'
            '    "template_names": [\n'
            '        "1ddc-4043-ac4d"\n'
            '    ]\n'
            '}')

    def test_save_new(self):
        project = Project(self.storage, name='example')
        spider = Spider(self.storage, id='test1', project=project)
        spider.save()

        self.storage.open.assert_not_called()
        self.storage.save.assert_called_once_with(
            'spiders/test1.json', mock.ANY)
        self.assertEqual(
            self.storage.files['spiders/test1.json'],
            '{\n'
            '    "allowed_domains": [], \n'
            '    "exclude_patterns": [], \n'
            '    "follow_patterns": [], \n'
            '    "id": "test1", \n'
            '    "js_disable_patterns": [], \n'
            '    "js_enable_patterns": [], \n'
            '    "js_enabled": false, \n'
            '    "links_to_follow": "all", \n'
            '    "respect_nofollow": true, \n'
            '    "start_urls": [], \n'
            '    "template_names": []\n'
            '}')

        project.spiders.insert(0, Spider(self.storage, id='test2'))
        project.spiders[0].save()

        self.storage.open.assert_not_called()
        self.assertEqual(self.storage.save.call_count, 2)
        self.storage.save.assert_has_calls([
            mock.call('spiders/test1.json', mock.ANY),
            mock.call('spiders/test2.json', mock.ANY)])
        self.assertEqual(
            self.storage.files['spiders/test2.json'],
            '{\n'
            '    "allowed_domains": [], \n'
            '    "exclude_patterns": [], \n'
            '    "follow_patterns": [], \n'
            '    "id": "test2", \n'
            '    "js_disable_patterns": [], \n'
            '    "js_enable_patterns": [], \n'
            '    "js_enabled": false, \n'
            '    "links_to_follow": "all", \n'
            '    "respect_nofollow": true, \n'
            '    "start_urls": [], \n'
            '    "template_names": []\n'
            '}')


class SampleTests(ProjectTestCase):
    def test_minimal_sample(self):
        sample = Sample(
            id='sample-1',
            name='example',
            url='http://example.com')

        self.assertEqual(sample.dump(), {
            'id': 'sample-1',
            'name': 'example',
            'url': 'http://example.com',
            'spider': None,
        })

    def test_full_sample(self):
        sample = Sample(
            id='sample-1',
            name='example',
            url='http://example.com',
            spider=Spider(id='spider-1'))

        self.assertEqual(sample.dump(), {
            'id': 'sample-1',
            'name': 'example',
            'url': 'http://example.com',
            'spider': 'spider-1',
        })

    def test_load_through_project(self):
        project = Project(self.storage, name='example')
        samples = project.spiders['shop-crawler'].samples
        self.assertListEqual(samples.keys(), ['1ddc-4043-ac4d'])
        self.assertIsInstance(samples, Sample.collection)
        self.storage.open.assert_called_once_with('spiders/shop-crawler.json')
        self.assertEqual(samples.dump(), [
            {
                'id': '1ddc-4043-ac4d',
                'name': 'example',
                'url': 'http://example.com',
                'spider': 'shop-crawler',
            },
        ])
        self.assertEqual(self.storage.open.call_count, 2)
        self.storage.open.assert_has_calls([
            mock.call('spiders/shop-crawler.json'),
            mock.call('spiders/shop-crawler/1ddc-4043-ac4d.json')])

    def test_load_through_partial(self):
        sample = Sample(self.storage, id='1ddc-4043-ac4d',
                        spider=Spider(self.storage, id='shop-crawler'))
        self.assertEqual(sample.dump(), {
            'id': '1ddc-4043-ac4d',
            'name': 'example',
            'url': 'http://example.com',
            'spider': 'shop-crawler',
        })
        self.assertEqual(self.storage.open.call_count, 2)
        self.storage.open.assert_has_calls([
            mock.call('spiders/shop-crawler.json'),
            mock.call('spiders/shop-crawler/1ddc-4043-ac4d.json')])
