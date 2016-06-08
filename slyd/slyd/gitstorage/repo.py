import os
import sys

from contextlib import contextmanager
from io import BytesIO

from dulwich.errors import NoIndexPresent
from dulwich.object_store import BaseObjectStore
from dulwich.objects import sha_to_hex
from dulwich.pack import (PackData, PackInflater, write_pack_header,
                          write_pack_object, PackIndexer, PackStreamCopier,
                          compute_file_sha)
from dulwich.repo import BaseRepo
from dulwich.refs import RefsContainer, SYMREF

from six.moves.urllib.parse import urlparse

from twisted.enterprise.adbapi import ConnectionPool, ConnectionLost

from slyd.projects import ProjectsManager
from slyd.projectspec import ProjectSpec


try:
    from MySQLdb import OperationalError
    ERRORS = (ConnectionLost, OperationalError, IOError)
except ImportError:
    ERRORS = (ConnectionLost, IOError)
    OperationalError = None
RETRIES = 3


class ReconnectionPool(ConnectionPool):
    '''This pool will reconnect if the server goes away or a deadlock occurs.

    This also injects a connection into `ProjectsManager` and `ProjectSpec`
    instances.

    [source] http://www.gelens.org/2009/09/13/twisted-connectionpool-revisited/
    [via] http://stackoverflow.com/questions/12677246/
    '''

    def _runWithConnection(self, func, *args, **kw):
        retries = kw.pop('_retries', 0)
        conn = self.connectionFactory(self)
        try:
            for manager in args:
                if isinstance(manager, (ProjectsManager, ProjectSpec)):
                    break
            setattr(manager, 'connection', conn)
            if getattr(manager, 'pm', None):
                setattr(manager.pm, 'connection', conn)
            if (not hasattr(manager, 'storage') and
                    hasattr(manager, 'project_name')):
                manager._open_repo()
        # Handle case where no manager is used
        except (AttributeError, UnboundLocalError):
            pass

        try:
            result = func(conn, *args, **kw)
            conn.commit()
            return result
        except ERRORS as e:
            # Connection should be re-acquired and transaction re-run when the
            # following OperationalErrors occur:
            #     1213: Deadlock found when trying to get lock
            #     2006: MySQL server has gone away
            #     2013: Lost connection to MySQL server during query
            if (retries >= RETRIES or isinstance(e, OperationalError) and
                    e[0] not in (2006, 2013, 1213)):
                raise
            try:
                conn.rollback()
            except:
                pass
            finally:
                conn.reconnect()

            kw['_retries'] = retries + 1
            return self._runWithConnection(func, *args, **kw)
        except:
            excType, excValue, excTraceback = sys.exc_info()
            try:
                conn.rollback()
            except:
                pass
            raise excType, excValue, excTraceback


@contextmanager
def closing_cursor(connection):
    cursor = connection.cursor()
    yield cursor
    cursor.close()


def _parse(url):
    """Parse a database URL."""
    url = urlparse(url)
    # Remove query strings.
    path = url.path[1:]
    path = path.split('?', 2)[0]
    config = {
        'host': url.hostname or '',
        'port': url.port or 3306,
        'db': path or '',
        'user': url.username or '',
        'passwd': url.password or '',
    }
    return config


connection_pool = None
DB_CONFIG = 'DB_URL' in os.environ and _parse(os.environ['DB_URL']) or {}
INIT_COMMAND = 'SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ'
POOL_NAME = 'PORTIA'
POOL_SIZE = 8
USE_PREPARED_STATEMENTS = False


def init_connection(connection):
    connection.autocommit(False)


def set_db_url(url):
    global DB_CONFIG
    DB_CONFIG = _parse(url)
    global connection_pool
    if connection_pool is None:
        connection_pool = ReconnectionPool(
            'MySQLdb', cp_reconnect=True, cp_min=3, cp_max=POOL_SIZE,
            cp_name=POOL_NAME, cp_openfun=init_connection,
            init_command=INIT_COMMAND,
            **DB_CONFIG)
    return connection_pool


class MysqlObjectStore(BaseObjectStore):
    """Object store that keeps all objects in a mysql database."""

    statements = {
        "HAS": "SELECT EXISTS(SELECT 1 FROM objs WHERE `oid`=%s AND `repo`=%s)",
        "ALL": "SELECT `oid` FROM objs WHERE `repo`=%s",
        "GET": "SELECT `type`, UNCOMPRESS(`data`) FROM objs WHERE `oid`=%s AND `repo`=%s",
        "ADD": "INSERT IGNORE INTO objs values(%s, %s, %s, COMPRESS(%s), %s)",
        "DEL": "DELETE FROM objs WHERE `oid`=%s AND `repo`=%s",
    }

    def __init__(self, repo, connection):
        super(MysqlObjectStore, self).__init__()
        self._repo = repo
        self.connection = connection

    def _to_hexsha(self, sha):
        if len(sha) == 40:
            return sha
        elif len(sha) == 20:
            return sha_to_hex(sha)
        else:
            raise ValueError("Invalid sha %r" % (sha,))

    def _has_sha(self, sha):
        """Look for the sha in the database."""
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlObjectStore.statements["HAS"],
                           (sha, self._repo))
            row = cursor.fetchone()
            return row[0] == 1

    def _all_shas(self):
        """Return all db sha keys."""
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlObjectStore.statements["ALL"], (self._repo,))
            shas = (t[0] for t in cursor.fetchall())
            return shas

    def contains_loose(self, sha):
        """Check if a particular object is present by SHA1 and is loose."""
        return self._has_sha(self._to_hexsha(sha))

    def contains_packed(self, sha):
        """Check if a particular object is present by SHA1 and is packed."""
        return False

    def __iter__(self):
        """Iterate over the SHAs that are present in this store."""
        return self._all_shas()

    @property
    def packs(self):
        """List with pack objects."""
        return []

    def get_raw(self, name):
        """Obtain the raw text for an object.

        :param name: sha for the object.
        :return: tuple with numeric type and object contents.
        """
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlObjectStore.statements["GET"],
                           (self._to_hexsha(name), self._repo))
            row = cursor.fetchone()
            return row

    def _add_object(self, obj):
        data = obj.as_raw_string()
        oid = obj.id
        tnum = obj.get_type()
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlObjectStore.statements["ADD"],
                           (oid, tnum, len(data), data, self._repo))

    def add_object(self, obj):
        self._add_object(obj)

    def add_objects(self, objects):
        """Add a set of objects to this object store.

        :param objects: Iterable over a list of objects.
        """
        with closing_cursor(self.connection) as cursor:
            for o, _ in objects:
                cursor.execute(MysqlObjectStore.statements["ADD"],
                               (o.id, o.get_type(), len(o.as_raw_string()),
                                o.as_raw_string(), self._repo))

    def delete_objects(self, object_ids):
        with closing_cursor(self.connection) as cursor:
            for oid in object_ids:
                cursor.execute(MysqlObjectStore.statements["DEL"],
                               (oid, self._repo))

    def add_pack(self, cursor):
        """Add a new pack to this object store.

        Because this object store doesn't support packs, we extract and add the
        individual objects.

        :return: Fileobject to write to and a commit function to
            call when the pack is finished.
        """
        f = BytesIO()

        def commit():
            p = PackData.from_file(BytesIO(f.getvalue()), f.tell())
            f.close()
            for obj in PackInflater.for_pack_data(p):
                self._add_object(obj, cursor)

        def abort():
            pass
        return f, commit, abort

    def _complete_thin_pack(self, f, indexer):
        """Complete a thin pack by adding external references.

        :param f: Open file object for the pack.
        :param indexer: A PackIndexer for indexing the pack.
        """
        entries = list(indexer)

        # Update the header with the new number of objects.
        f.seek(0)
        write_pack_header(f, len(entries) + len(indexer.ext_refs()))

        # Rescan the rest of the pack, computing the SHA with the new header.
        new_sha = compute_file_sha(f, end_ofs=-20)

        # Complete the pack.
        for ext_sha in indexer.ext_refs():
            assert len(ext_sha) == 20
            type_num, data = self.get_raw(ext_sha)
            write_pack_object(f, type_num, data, sha=new_sha)
        pack_sha = new_sha.digest()
        f.write(pack_sha)

    def add_thin_pack(self, read_all, read_some):
        """Add a new thin pack to this object store.

        Thin packs are packs that contain deltas with parents that exist
        outside the pack. Because this object store doesn't support packs, we
        extract and add the individual objects.

        :param read_all: Read function that blocks until the number of
            requested bytes are read.
        :param read_some: Read function that returns at least one byte, but may
            not return the number of bytes requested.
        """
        f, commit, abort = self.add_pack()
        try:
            indexer = PackIndexer(f, resolve_ext_ref=self.get_raw)
            copier = PackStreamCopier(read_all, read_some, f,
                                      delta_iter=indexer)
            copier.verify()
            self._complete_thin_pack(f, indexer)
        except:
            abort()
            raise
        else:
            commit()


class MysqlRefsContainer(RefsContainer):
    """RefsContainer backed by MySql.

    This container does not support packed references.
    """

    statements = {
        "DEL": "DELETE FROM `refs` WHERE `ref`=%s AND `repo`=%s",
        "ALL": "SELECT `ref` FROM `refs` WHERE `repo`=%s",
        "GET": "SELECT `value` FROM `refs` WHERE `ref` = %s AND `repo`=%s FOR UPDATE",
        "ADD": "REPLACE INTO `refs` VALUES(%s, %s, %s)",
    }

    def __init__(self, repo, connection):
        super(MysqlRefsContainer, self).__init__()
        self._repo = repo
        self.connection = connection
        self._peeled = {}

    def allkeys(self):
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlRefsContainer.statements["ALL"],
                           (self._repo,))
            return (t[0] for t in cursor.fetchall())

    def read_loose_ref(self, name, cursor=None):
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlRefsContainer.statements["GET"],
                           (name, self._repo))
            row = cursor.fetchone()
            sha = row[0] if row else None
            return sha

    def get_packed_refs(self):
        return {}

    def _update_ref(self, name, value):
        with closing_cursor(self.connection) as cursor:
            cursor.execute(MysqlRefsContainer.statements["ADD"],
                           (name, value, self._repo))

    def set_if_equals(self, name, old_ref, new_ref):
        if old_ref is not None:
            current_ref = self.read_loose_ref(name)
            if old_ref != current_ref:
                return False
        realname, _ = self._follow(name)
        self._check_refname(realname)
        self._update_ref(realname, new_ref)
        return True

    def set_symbolic_ref(self, name, other):
        self._update_ref(name, SYMREF + other)

    def add_if_new(self, name, ref):
        if self.read_loose_ref(name):
            return False
        self._update_ref(name, ref)
        return True

    def _remove_ref(self, cursor, name):
        cursor.execute(MysqlRefsContainer.statements["DEL"],
                       (name, self._repo))

    def remove_if_equals(self, name, old_ref):
        if old_ref is not None:
            current_ref = self.read_loose_ref(name)
            if current_ref != old_ref:
                return False
        with closing_cursor(self.connection) as cursor:
            self._remove_ref(cursor, name)
            return True

    def get_peeled(self, name):
        return self._peeled.get(name)


class MysqlRepo(BaseRepo):
    """Repo that stores refs, objects, and named files in MySql.

    MySql repos are always bare: they have no working tree and no index, since
    those have a stronger dependency on the filesystem.
    """

    def __init__(self, name, connection):
        self._name = name
        BaseRepo.__init__(self, MysqlObjectStore(name, connection),
                          MysqlRefsContainer(name, connection))
        self.connection = connection
        self.bare = True

    def open_index(self):
        """Fail to open index for this repo, since it is bare.

        :raise NoIndexPresent: Raised when no index is present
        """
        raise NoIndexPresent()

    def head(self):
        """Return the SHA1 pointed at by HEAD."""
        return self.refs['refs/heads/master']

    @classmethod
    def _init_db(cls, connection):
        with closing_cursor(connection) as cursor:
            # Object store table.
            sql = ('CREATE TABLE IF NOT EXISTS `objs` ('
                   '  `oid` binary(40) NOT NULL DEFAULT "",'
                   '  `type` tinyint(1) unsigned NOT NULL,'
                   '  `size` bigint(20) unsigned NOT NULL,'
                   '  `data` longblob NOT NULL,'
                   '  `repo` varchar(64) NOT NULL,'
                   '  PRIMARY KEY (`oid`, `repo`),'
                   '  KEY `type` (`type`),'
                   '  KEY `size` (`size`)'
                   ') ENGINE="InnoDB" DEFAULT CHARSET=utf8 COLLATE=utf8_bin')
            cursor.execute(sql)

            # Reference store table.
            sql = ('CREATE TABLE IF NOT EXISTS `refs` ('
                   '  `ref` varchar(100) NOT NULL DEFAULT "",'
                   '  `value` binary(40) NOT NULL,'
                   '  `repo` varchar(64) NOT NULL,'
                   '  PRIMARY KEY (`ref`, `repo`),'
                   '  KEY `value` (`value`)'
                   ') ENGINE="InnoDB" DEFAULT CHARSET=utf8 COLLATE=utf8_bin')
            cursor.execute(sql)

    @classmethod
    def setup(cls, location):
        return set_db_url(location)

    @classmethod
    def init_bare(cls, name, connection):
        """Create a new bare repository."""
        return cls(name, connection)

    @classmethod
    def open(cls, name, connection):
        """Open an existing repository."""
        return cls(name, connection)

    @classmethod
    def repo_exists(cls, name, connection):
        """Check if a repository exists."""
        with closing_cursor(connection) as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM `objs` "
                           "WHERE `repo`=%s)", (name,))
            row = cursor.fetchone()
        if row:
            return row[0] == 1
        return False

    @classmethod
    def list_repos(cls, connection):
        """List all repository names."""
        with closing_cursor(connection) as cursor:
            cursor.execute("SELECT DISTINCT `repo` FROM `objs`")
            return [t[0] for t in cursor.fetchall()]

    @classmethod
    def delete_repo(cls, name, connection):
        """Delete a repository."""
        with closing_cursor(connection) as cursor:
            cursor.execute("DELETE FROM `objs` WHERE `repo`=%s", (name,))
            cursor.execute("DELETE FROM `refs` WHERE `repo`=%s", (name,))
