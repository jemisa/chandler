
__revision__  = "$Revision$"
__date__      = "$Date$"
__copyright__ = "Copyright (c) 2002 Open Source Applications Foundation"
__license__   = "http://osafoundation.org/Chandler_0.1_license_terms.htm"

import sys, threading

from struct import pack, unpack

from chandlerdb.util.c import UUID, _hash, SkipList
from chandlerdb.persistence.c import \
    DBSequence, DB, \
    CContainer, CValueContainer, CRefContainer, CItemContainer, \
    DBNotFoundError, DBLockDeadlockError, DBNoSuchFileError

from repository.item.Access import ACL, ACE
from repository.item.Item import Item
from repository.persistence.Repository import Repository
from repository.persistence.RepositoryView import RepositoryView
from repository.persistence.RepositoryError import \
    RepositoryFormatVersionError, RepositorySchemaVersionError


class DBContainer(object):

    def __init__(self, store):

        self.store = store
        self._db = None

    def openDB(self, txn, name, dbname, ramdb, create):

        db = DB(self.store.env)
        db.lorder = 4321
        
        if ramdb:
            name = None
            dbname = None

        if create:
            db.open(filename = name, dbname = dbname,
                    dbtype = DB.DB_BTREE,
                    flags = DB.DB_CREATE | DB.DB_THREAD | self._flags,
                    txn = txn)
        else:
            db.open(filename = name, dbname = dbname, 
                    dbtype = DB.DB_BTREE,
                    flags = DB.DB_THREAD | self._flags,
                    txn = txn)

        return db

    def openC(self):

        self.c = CContainer(self._db)

    def open(self, name, txn, **kwds):

        self._threaded = threading.local()
        self._flags = 0

        self._db = self.openDB(txn, name, kwds.get('dbname', None),
                               kwds.get('ramdb', False),
                               kwds.get('create', False))
        self.openC()

    def openIndex(self, name, dbname, txn, **kwds):

        index = self.openDB(txn, name, dbname,
                            kwds.get('ramdb', False),
                            kwds.get('create', False))

        self.associateIndex(index, dbname, txn)

        return index

    def associateIndex(self, index, name, txn):

        raise NotImplementedError, "%s.associateIndex" %(type(self))

    def close(self):

        if self._db is not None:
            self._db.close()
            self._db = None
        self._threaded = None

    def compact(self, txn):

        self._db.compact(txn)

    def attachView(self, view):

        pass

    def detachView(self, view):

        pass

    def put(self, key, value):

        self._db.put(key, value, self.store.txn)
        return len(key) + len(value)

    def delete(self, key, txn=None):

        try:
            self._db.delete(key, txn or self.store.txn)
        except DBNotFoundError:
            pass

    def get(self, key):

        while True:
            try:
                return self._db.get(key, self.store.txn, self._flags, None)
            except DBLockDeadlockError:
                self._logDL(24)
                if self.store.txn is not None:
                    raise

    def openCursor(self, db=None):

        if db is None:
            db = self._db

        try:
            cursor = self._threaded.cursors.get(db, None)
            if cursor is not None:
                return cursor.dup()
        except AttributeError:
            self._threaded.cursors = {}
        
        cursor = db.cursor(self.store.txn, self._flags)
        self._threaded.cursors[db] = cursor

        return cursor

    def closeCursor(self, cursor, db=None):

        if cursor is not None:

            if db is None:
                db = self._db

            try:
                if self._threaded.cursors.get(db, None) is cursor:
                    del self._threaded.cursors[db]
            except AttributeError:
                pass
            except KeyError:
                pass
                
            cursor.close()

    def _logDL(self, n):

        self.store.repository.logger.info('detected deadlock: %d', n)

    def _readValue(self, value, offset):

        code = value[offset]
        offset += 1

        if code == '\0':
            return (1, None)

        if code == '\1':
            return (1, True)

        if code == '\2':
            return (1, False)

        if code == '\3':
            return (17, UUID(value[offset:offset+16]))

        if code == '\4':
            return (5, unpack('>l', value[offset:offset+4])[0])

        if code == '\5':
            l, = unpack('>H', value[offset:offset+2])
            offset += 2
            return (l + 3, value[offset:offset+l])

        if code == '\6':
            l, = unpack('>H', value[offset:offset+2])
            offset += 2
            return (l + 3, unicode(value[offset:offset+l], 'utf-8'))

        raise ValueError, code

    def _writeUUID(self, buffer, value):

        if value is None:
            buffer.append('\0')
        else:
            buffer.append('\3')
            buffer.append(value._uuid)

    def _writeString(self, buffer, value):

        if value is None:
            buffer.append('\0')
        
        elif isinstance(value, str):
            buffer.append('\5')
            buffer.append(pack('>H', len(value)))
            buffer.append(value)

        elif isinstance(value, unicode):
            value = value.encode('utf-8')
            buffer.append('\5')
            buffer.append(pack('>H', len(value)))
            buffer.append(value)

        else:
            raise TypeError, type(value)

    def _writeBoolean(self, buffer, value):

        if value is True:
            buffer.append('\1')

        elif value is False:
            buffer.append('\2')
        
        else:
            raise TypeError, type(value)

    def _writeInteger(self, buffer, value):

        if value is None:
            buffer.append('\0')
        
        buffer.append('\4')
        buffer.append(pack('>l', value))

    def _writeValue(self, buffer, value):

        if value is None:
            buffer.append('\0')

        elif value is True or value is False:
            self._writeBoolean(buffer, value)

        elif isinstance(value, str) or isinstance(value, unicode):
            self._writeString(buffer, value)

        elif isinstance(value, int) or isinstance(value, long):
            self._writeInteger(buffer, value)

        elif isinstance(value, UUID):
            self._writeUUID(buffer, value)

        else:
            raise NotImplementedError, "value: %s, type: %s" %(value,
                                                               type(value))


class RefContainer(DBContainer):

    def __init__(self, store):

        super(RefContainer, self).__init__(store)
        self._history = None
        
    def open(self, name, txn, **kwds):

        super(RefContainer, self).open(name, txn, dbname = 'data', **kwds)
        self._history = self.openIndex(name, 'history', txn, **kwds)

    def associateIndex(self, index, name, txn):

        self.c.associateHistory(index, txn, DB.DB_IMMUTABLE_KEY)

    def openC(self):

        self.c = CRefContainer(self._db)

    def close(self):

        if self._history is not None:
            self._history.close()
            self._history = None

        super(RefContainer, self).close()

    def compact(self, txn):

        super(RefContainer, self).compact(txn)
        self._history.compact(txn)

    def applyHistory(self, view, fn, uuid, oldVersion, newVersion):

        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor(self._history)

                try:
                    value = cursor.set_range(pack('>16sq', uuid._uuid,
                                                  oldVersion + 1),
                                             self._flags, None)
                    if value is None:
                        return

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(16)
                        continue
                    else:
                        raise

                try:
                    while value is not None:
                        uCol, version, uRef = unpack('>16sq16s', value[0])
                        if version > newVersion or uCol != uuid._uuid:
                            break

                        fn(version, (UUID(uCol), UUID(uRef)),
                           self._readRef(value[1]))

                        value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(17)
                        continue
                    else:
                        raise

                return

            finally:
                self.closeCursor(cursor, self._history)
                store.abortTransaction(view, txnStatus)

    def deleteRef(self, uCol, version, uRef):

        return self.put(pack('>16s16sq', uCol._uuid, uRef._uuid,
                             ~version), '\0')

    def _readRef(self, value):

        if len(value) == 1:   # deleted ref
            return None

        else:
            offset = 0

            l, previous = self._readValue(value, offset)
            offset += l

            l, next = self._readValue(value, offset)
            offset += l

            l, alias = self._readValue(value, offset)
            offset += l

            return (previous, next, alias)

    def loadRef(self, view, uCol, version, uRef):

        store = self.store

        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()

                try:
                    return self.c.loadRef(cursor, uCol._uuid, uRef._uuid,
                                          version, self._flags)
                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(1)
                        continue
                    else:
                        raise
            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)

    def refIterator(self, view, uCol, version):

        store = self.store

        class _iterator(object):

            def __init__(_self):

                _self.txnStatus = store.startTransaction(view)
                _self.cursor = self.openCursor()

            def __del__(_self):

                try:
                    self.closeCursor(_self.cursor)
                    store.commitTransaction(view, _self.txnStatus)
                except Exception, e:
                    store.repository.logger.error("in 0 __del__, %s: %s",
                                                  e.__class__.__name__, e)
                _self.cursor = None
                _self.txnStatus = 0

            def next(_self, uRef):

                try:
                    return self.c.loadRef(_self.cursor, uCol._uuid, uRef._uuid,
                                          version, self._flags)
                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(27)
                        return True
                    else:
                        raise

        return _iterator()

    def purgeRefs(self, txn, uCol, keepOne):

        count = 0
        cursor = None

        try:
            cursor = self.openCursor()
            key = uCol._uuid
            value = cursor.set_range(key, self._flags, None)

            if not keepOne:
                while value is not None and value[0].startswith(key):
                    cursor.delete(self._flags)
                    count += 1
                    value = cursor.next(self._flags, None)

            else:
                prevRef = None
                while value is not None and value[0].startswith(key):
                    ref = value[0][16:32]
                    if ref == prevRef or len(value[1]) == 1:
                        cursor.delete(self._flags)
                        count += 1
                    prevRef = ref
                    value = cursor.next(self._flags, None)

        finally:
            self.closeCursor(cursor)

        return count, self.store._names.purgeNames(txn, uCol, keepOne)


class NamesContainer(DBContainer):

    def writeName(self, version, key, name, uuid):

        if name is None:
            raise ValueError, 'name is None'
        
        if isinstance(name, unicode):
            name = name.encode('utf-8')
            
        if uuid is None:
            uuid = key

        return self.put(pack('>16slq', key._uuid, _hash(name), ~version),
                        uuid._uuid)

    def purgeNames(self, txn, uuid, keepOne):

        count = 0
        cursor = None

        try:
            cursor = self.openCursor()
            key = uuid._uuid
            prevHash = None
            value = cursor.set_range(key, self._flags, None)

            if not keepOne:
                while value is not None and value[0].startswith(key):
                    cursor.delete(self._flags)
                    count += 1
                    value = cursor.next(self._flags, None)

            else:
                while value is not None and value[0].startswith(key):
                    hash = value[0][16:20]
                    if hash == prevHash or key == value[1]:
                        cursor.delete(self._flags)
                        count += 1
                    prevHash = hash
                    value = cursor.next(self._flags, None)

        finally:
            self.closeCursor(cursor)

        return count

    def readName(self, view, version, key, name):

        if name is None:
            raise ValueError, 'name is None'
        
        if isinstance(name, unicode):
            name = name.encode('utf-8')

        cursorKey = pack('>16sl', key._uuid, _hash(name))
        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()
                
                try:
                    value = cursor.set_range(cursorKey, self._flags, None)
                    if value is None:
                        return None

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(8)
                        continue
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(cursorKey):
                        nameVer = ~unpack('>q', value[0][-8:])[0]
                
                        if nameVer <= version:
                            if value[1] == value[0][0:16]:    # deleted name
                                return None

                            return UUID(value[1])

                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(9)
                        continue
                    else:
                        raise

                return None

            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)

    def readNames(self, view, version, key):

        results = []
        cursorKey = key._uuid
        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()
                
                try:
                    value = cursor.set_range(cursorKey, self._flags, None)
                    if value is None:
                        return results

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(12)
                        continue
                    else:
                        raise

                currentHash = None
                
                try:
                    while value is not None and value[0].startswith(cursorKey):
                        nameHash, nameVer = unpack('>lq', value[0][-12:])
                
                        if nameHash != currentHash and ~nameVer <= version:
                            currentHash = nameHash

                            if value[1] != value[0][0:16]:    # !deleted name
                                results.append(UUID(value[1]))

                        value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(13)
                        continue
                    else:
                        raise

                return results

            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)


class ACLContainer(DBContainer):

    def writeACL(self, version, key, name, acl):

        if name is None:
            key = pack('>16slq', key._uuid, 0, ~version)
        else:
            if isinstance(name, unicode):
                name = name.encode('utf-8')
            key = pack('>16slq', key._uuid, _hash(name), ~version)

        if acl is None:    # deleted acl
            value = '\0\0\0\0'
        else:
            value = "".join([pack('>16sl', ace.pid._uuid, ace.perms)
                             for ace in acl])

        self.put(key, value)

    def readACL(self, view, version, key, name):

        if name is None:
            cursorKey = pack('>16sl', key._uuid, 0)
        else:
            if isinstance(name, unicode):
                name = name.encode('utf-8')
            cursorKey = pack('>16sl', key._uuid, _hash(name))

        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()
                
                try:
                    value = cursor.set_range(cursorKey, self._flags, None)
                    if value is None:
                        return None

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(10)
                        continue
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(cursorKey):
                        key, aces = value
                        aclVer = ~unpack('>q', key[-8:])[0]
                
                        if aclVer <= version:
                            if len(aces) == 4:    # deleted acl
                                return None

                            acl = ACL()
                            for i in xrange(0, len(aces), 20):
                                pid = UUID(aces[i:i+16])
                                perms = unpack('>l', aces[i+16:i+20])[0]
                                acl.append(ACE(pid, perms))

                            return acl
                        
                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(11)
                        continue
                    else:
                        raise

                return None

            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)


class IndexesContainer(DBContainer):

    def _packKey(self, buffer, key, version=None):

        if version is None:
            return buffer + key._uuid

        return buffer + key._uuid + pack('>q', ~version)

    def saveKey(self, keyBuffer, version, key, node):

        buffer = []

        if node is not None:
            level = len(node)
            buffer.append(pack('b', level))
            buffer.append(pack('>l', node._entryValue))
            for lvl in xrange(1, level + 1):
                point = node[lvl]
                self._writeUUID(buffer, point.prevKey)
                self._writeUUID(buffer, point.nextKey)
                buffer.append(pack('>l', point.dist))
        else:
            buffer.append('\0')
            
        return self.put(self._packKey(keyBuffer, key, version), ''.join(buffer))

    def loadKey(self, view, keyBuffer, version, key):
        
        cursorKey = self._packKey(keyBuffer, key)
        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()

                try:
                    value = cursor.set_range(cursorKey, self._flags, None)
                    if value is None:
                        return None

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(14)
                        continue
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(cursorKey):
                        keyVer = ~unpack('>q', value[0][32:40])[0]
                
                        if keyVer <= version:
                            value = value[1]
                            level = unpack('b', value[0])[0]

                            if level == 0:
                                return None
                    
                            node = SkipList.Node(level)
                            node._entryValue = unpack('>l', value[1:5])[0]
                            offset = 5
                            
                            for lvl in xrange(1, level + 1):
                                point = node[lvl]

                                l, prevKey = self._readValue(value, offset)
                                offset += l
                                l, nextKey = self._readValue(value, offset)
                                offset += l
                                dist = unpack('>l', value[offset:offset+4])[0]
                                offset += 4

                                point.prevKey = prevKey
                                point.nextKey = nextKey
                                point.dist = dist

                            return node
                        
                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(15)
                        continue
                    else:
                        raise

                return None

            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)

    def purgeIndex(self, txn, uIndex, keepOne):

        count = 0
        cursor = None

        try:
            cursor = self.openCursor()
            key = uIndex._uuid
            value = cursor.set_range(key, self._flags, None)

            if not keepOne:
                while value is not None and value[0].startswith(key):
                    cursor.delete(self._flags)
                    count += 1
                    value = cursor.next(self._flags, None)

            else:
                prevRef = None
                while value is not None and value[0].startswith(key):
                    ref = value[0][16:32]
                    if ref == prevRef or value[1][0] == '\0':
                        cursor.delete(self._flags)
                        count += 1
                    prevRef = ref
                    value = cursor.next(self._flags, None)

        finally:
            self.closeCursor(cursor)

        return count

    def nodeIterator(self, view, keyBuffer, version):
        
        store = self.store

        class _iterator(object):

            def __init__(_self):

                _self.txnStatus = store.startTransaction(view)
                _self.cursor = self.openCursor()

            def __del__(_self):

                try:
                    self.closeCursor(_self.cursor)
                    store.commitTransaction(view, _self.txnStatus)
                except Exception, e:
                    store.repository.logger.error("in 1 __del__, %s: %s",
                                                  e.__class__.__name__, e)
                _self.cursor = None
                _self.txnStatus = 0

            def next(_self, key):

                try:
                    cursorKey = self._packKey(keyBuffer, key)
                    value = _self.cursor.set_range(cursorKey, self._flags, None)
                    if value is None:
                        return None
                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(25)
                        return True
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(cursorKey):
                        keyVer = ~unpack('>q', value[0][32:40])[0]
                
                        if keyVer <= version:
                            value = value[1]
                            level = unpack('b', value[0])[0]

                            if level == 0:
                                return False
                    
                            node = SkipList.Node(level)
                            node._entryValue = unpack('>l', value[1:5])[0]
                            offset = 5
                            
                            for lvl in xrange(1, level + 1):
                                point = node[lvl]

                                l, prevKey = self._readValue(value, offset)
                                offset += l
                                l, nextKey = self._readValue(value, offset)
                                offset += l
                                dist = unpack('>l', value[offset:offset+4])[0]
                                offset += 4

                                point.prevKey = prevKey
                                point.nextKey = nextKey
                                point.dist = dist

                            return node
                        
                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(15)
                        return True
                    else:
                        raise

        return _iterator()


class ItemContainer(DBContainer):

    def __init__(self, store):

        super(ItemContainer, self).__init__(store)

        self._kinds = None
        self._versions = None
        
    def open(self, name, txn, **kwds):

        super(ItemContainer, self).open(name, txn, dbname = 'data', **kwds)

        self._kinds = self.openIndex(name, 'kinds', txn, **kwds)
        self._versions = self.openIndex(name, 'versions', txn, **kwds)

    def associateIndex(self, index, name, txn):

        if name == 'kinds':
            self.c.associateKind(index, txn, DB.DB_IMMUTABLE_KEY)
        elif name == 'versions':
            self.c.associateVersion(index, txn, DB.DB_IMMUTABLE_KEY)
        else:
            raise ValueError, name

    def openC(self):

        self.c = CItemContainer(self._db)

    def close(self):

        if self._kinds is not None:
            self._kinds.close()
            self._kinds = None

        if self._versions is not None:
            self._versions.close()
            self._versions = None

        super(ItemContainer, self).close()

    def compact(self, txn):

        super(ItemContainer, self).compact(txn)

        self._kinds.compact(txn)
        self._versions.compact(txn)

    def saveItem(self, buffer, uItem, version, uKind, status,
                 uParent, name, moduleName, className,
                 values, dirtyValues, dirtyRefs):

        del buffer[:]

        buffer.append(uKind._uuid)
        buffer.append(pack('>l', status))
        buffer.append(uParent._uuid)

        self._writeString(buffer, name)
        self._writeString(buffer, moduleName)
        self._writeString(buffer, className)

        def writeName(name):
            if isinstance(name, unicode):
                name = name.encode('utf-8')
            buffer.append(pack('>l', _hash(name)))
            
        for name, uValue in values:
            writeName(name)
            buffer.append(uValue._uuid)

        count = 0
        for name in dirtyValues:
            writeName(name)
            count += 1
        for name in dirtyRefs:
            writeName(name)
            count += 1
        buffer.append(pack('>l', len(values)))
        buffer.append(pack('>l', count))

        # (uItem, version), (uKind, status, uParent, ...)

        return self.put(pack('>16sq', uItem._uuid, ~version), ''.join(buffer))

    def _readItem(self, itemVer, value):

        uKind = UUID(value[0:16])
        status, = unpack('>l', value[16:20])
        uParent = UUID(value[20:36])
        
        offset = 36
        l, name = self._readValue(value, offset)
        offset += l
        l, moduleName = self._readValue(value, offset)
        offset += l
        l, className = self._readValue(value, offset)
        offset += l

        count, = unpack('>l', value[-8:-4])
        values = []
        for i in xrange(count):
            values.append(UUID(value[offset+4:offset+20]))
            offset += 20

        return (itemVer, uKind, status, uParent, name,
                moduleName, className, values)

    def _itemFinder(self, view):

        store = self.store

        class _finder(object):

            def __init__(_self):

                _self.txnStatus = store.startTransaction(view)
                _self.cursor = self.openCursor()

            def __del__(_self):

                try:
                    self.closeCursor(_self.cursor)
                    store.commitTransaction(view, _self.txnStatus)
                except Exception, e:
                    store.repository.logger.error("in 2 __del__, %s: %s",
                                                  e.__class__.__name__, e)
                _self.cursor = None
                _self.txnStatus = 0

            def _find(_self, version, uuid):

                key = uuid._uuid

                try:
                    value = _self.cursor.set_range(key, self._flags, None)
                    if value is None:
                        return None, None
                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(27)
                        return True, None
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(key):
                        itemVer = ~unpack('>q', value[0][16:24])[0]
                
                        if itemVer <= version:
                            return itemVer, value[1]
                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(28)
                        return True, None
                    else:
                        raise

                return None, None

            def findItem(_self, version, uuid):

                while True:
                    v, i = _self._find(version, uuid)
                    if v is True:
                        continue
                    if i is None:
                        return None, None
                    return v, i

            def getVersion(_self, version, uuid):

                while True:
                    v, i = _self._find(version, uuid)
                    if v is True:
                        continue
                    if i is None:
                        return None
                    return v

        return _finder()

    def _findItem(self, view, version, uuid):

        key = uuid._uuid
        store = self.store

        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor()

                try:
                    value = cursor.set_range(key, self._flags, None)
                    if value is None:
                        return None, None

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(20)
                        continue
                    else:
                        raise

                try:
                    while value is not None and value[0].startswith(key):
                        itemVer = ~unpack('>q', value[0][16:24])[0]
                
                        if itemVer <= version:
                            return itemVer, value[1]
                        else:
                            value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(21)
                        continue
                    else:
                        raise

                return None, None

            finally:
                self.closeCursor(cursor)
                store.abortTransaction(view, txnStatus)

    def getItemValues(self, version, uuid):

        item = self.get(pack('>16sq', uuid._uuid, ~version))
        if item is None:
            return None

        vCount, dCount = unpack('>ll', item[-8:])
        offset = -(vCount * 20 + dCount * 4 + 8)
        values = {}

        for i in xrange(vCount):
            hash, uuid = unpack('>l16s', item[offset:offset+20])
            values[hash] = UUID(uuid)
            offset += 20

        return values

    def loadItem(self, view, version, uuid):

        version, item = self._findItem(view, version, uuid)
        if item is not None:
            return self._readItem(version, item)

        return None

    def purgeItem(self, txn, uuid, version):

        self.delete(pack('>16sq', uuid._uuid, ~version), txn)
        return 1

    def findValue(self, view, version, uuid, name):

        version, item = self._findItem(view, version, uuid)
        if item is not None:

            if isinstance(name, unicode):
                name = name.encode('utf-8')
            hash = _hash(name)

            vCount, dCount = unpack('>ll', item[-8:])
            pos = -(dCount + 2) * 4 - vCount * 20

            for i in xrange(vCount):
                h, uValue = unpack('>l16s', item[pos:pos+20])
                if h == hash:
                    return unpack('>l', item[16:20])[0], UUID(uValue)
                pos += 20

        return None, None

    def getItemParentId(self, view, version, uuid):

        version, item = self._findItem(view, version, uuid)
        if item is not None:
            return UUID(item[20:36])

        return None

    def getItemKindId(self, view, version, uuid):

        version, item = self._findItem(view, version, uuid)
        if item is not None:
            return UUID(item[0:16])

        return None

    def getItemVersion(self, view, version, uuid):

        version, item = self._findItem(view, version, uuid)
        if item is not None:
            return version

        return None

    def kindQuery(self, view, version, uuid, keysOnly=False):

        store = self.store

        class _query(object):

            def __init__(_self):

                _self.cursor = None
                _self.txnStatus = 0

            def __del__(_self):

                try:
                    self.closeCursor(_self.cursor, self._kinds)
                    store.commitTransaction(view, _self.txnStatus)
                except Exception, e:
                    store.repository.logger.error("in __del__, %s: %s",
                                                  e.__class__.__name__, e)
                _self.cursor = None
                _self.txnStatus = 0

            def run(_self):

                _self.txnStatus = store.startTransaction(view)
                _self.cursor = self.openCursor(self._kinds)
                
                try:
                    value = _self.cursor.set_range(uuid._uuid, self._flags,
                                                   None)
                    if value is None:
                        yield False

                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(22)
                        yield True
                    else:
                        raise

                try:
                    lastItem = None
                    while value is not None:
                        uKind, uItem, vItem = unpack('>16s16sq', value[0])
                        if uKind != uuid._uuid:
                            break

                        vItem = ~vItem
                        if vItem <= version and uItem != lastItem:
                            if keysOnly:
                                yield UUID(uItem), vItem
                            else:
                                args = self._readItem(vItem, value[1])
                                yield UUID(uItem), args
                            lastItem = uItem

                        value = _self.cursor.next(self._flags, None)

                    yield False

                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(23)
                        yield True
                    else:
                        raise

        while True:
            for result in _query().run():
                if result is True:
                    break
                if result is False:
                    return
                yield result

    def applyHistory(self, view, fn, oldVersion, newVersion):

        store = self.store
        
        while True:
            txnStatus = 0
            cursor = None

            try:
                txnStatus = store.startTransaction(view)
                cursor = self.openCursor(self._versions)

                try:
                    value = cursor.set_range(pack('>q', oldVersion + 1),
                                             self._flags, None)
                    if value is None:
                        return

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(18)
                        continue
                    else:
                        raise

                try:
                    while value is not None:
                        version, uuid = unpack('>q16s', value[0])
                        if version > newVersion:
                            break

                        value = value[1]
                        status, parentId = unpack('>l16s', value[16:36])

                        if status & Item.DELETED:
                            dirties = HashTuple()
                        else:
                            pos = -(unpack('>l', value[-4:])[0] + 2) << 2
                            value = value[pos:-8]
                            dirties = unpack('>%dl' %(len(value) >> 2), value)
                            dirties = HashTuple(dirties)

                        fn(UUID(uuid), version, status, UUID(parentId), dirties)

                        value = cursor.next(self._flags, None)

                except DBLockDeadlockError:
                    if txnStatus & store.TXN_STARTED:
                        self._logDL(19)
                        continue
                    else:
                        raise

                return

            finally:
                self.closeCursor(cursor, self._versions)
                store.abortTransaction(view, txnStatus)

    def iterItems(self, view):

        store = self.store
        
        class _iterator(object):

            def __init__(_self):

                _self.cursor = None
                _self.txnStatus = 0

            def __del__(_self):

                try:
                    self.closeCursor(_self.cursor)
                    store.commitTransaction(view, _self.txnStatus)
                except Exception, e:
                    store.repository.logger.error("in __del__, %s: %s",
                                                  e.__class__.__name__, e)
                _self.cursor = None
                _self.txnStatus = 0

            def next(_self):

                _self.txnStatus = store.startTransaction(view)
                _self.cursor = self.openCursor()
                
                try:
                    while True:
                        value = _self.cursor.next(self._flags, None)
                        if value is None:
                            break

                        uuid, version = unpack('>16sq', value[0])

                        value = value[1]
                        status, = unpack('>l', value[16:20])
                        vCount, dCount = unpack('>ll', value[-8:])
                        offset = -(vCount * 20 + dCount * 4 + 8)

                        values = []
                        for i in xrange(vCount):
                            values.append(UUID(value[offset+4:offset+20]))
                            offset += 20

                        yield (UUID(uuid), ~version, status, values)

                    yield False

                except DBLockDeadlockError:
                    if _self.txnStatus & store.TXN_STARTED:
                        self._logDL(28)
                        yield True
                    else:
                        raise

        while True:
            for result in _iterator().next():
                if result is True:
                    break
                if result is False:
                    return
                yield result


class ValueContainer(DBContainer):

    # 0.5.0: first tracked format version
    # 0.5.1: 'Long' values saved as long long (64 bit)
    # 0.5.2: added support for 'Set' type and 'set' cardinality
    # 0.5.3: added core schema version to version info
    # 0.5.4: endianness on index dbs set to 4321
    # 0.5.5: lob 'indexed' attribute now saved as -1, 0, 1
    # 0.5.6: lob encryption reworked to include IV
    # 0.5.7: string length incremented before saved to preserve sign
    # 0.5.8: date/time type formats optimized
    # 0.5.9: value flags and enum values saved as byte instead of int
    # 0.5.10: added support for storing selection ranges on indexes
    # 0.6.0: version reimplemented as 64 bit sequence, removed value index
    # 0.6.1: version purge support

    FORMAT_VERSION = 0x00060100

    def __init__(self, store):

        super(ValueContainer, self).__init__(store)
        self._versionSeq = None
        
    def open(self, name, txn, **kwds):

        super(ValueContainer, self).open(name, txn, dbname = 'data', **kwds)

        format_version = ValueContainer.FORMAT_VERSION
        schema_version = RepositoryView.CORE_SCHEMA_VERSION

        try:
            self._version = self.openDB(txn, name, 'version',
                                        kwds.get('ramdb', False),
                                        kwds.get('create', False))
        except DBNoSuchFileError:
            # pre 0.6.0
            raise RepositoryFormatVersionError, (format_version, 'pre 0.6.0')

        self._versionSeq = versionSeq = DBSequence(self._version)

        if kwds.get('create', False):
            versionId = UUID()
            versionSeq.initial_value = 0
            versionSeq.open(txn, versionId._uuid,
                            DBSequence.DB_CREATE | DBSequence.DB_THREAD)
            versionSeq.get(txn)
            self._version.put(Repository.itsUUID._uuid,
                              pack('>16sll', versionId._uuid,
                                   format_version, schema_version), txn)
        else:
            values = self.getVersionInfo(Repository.itsUUID, txn, True)
            if values[2] != format_version:
                raise RepositoryFormatVersionError, (format_version, values[2])
            if values[3] != schema_version:
                raise RepositorySchemaVersionError, (schema_version, values[3])

    def openC(self):

        self.c = CValueContainer(self._db)

    def close(self):

        if self._versionSeq is not None:
            self._versionSeq.close()
            self._versionSeq = None

        if self._version is not None:
            self._version.close()
            self._version = None

        super(ValueContainer, self).close()

    def compact(self, txn):

        super(ValueContainer, self).compact(txn)
        self._version.compact(txn)

    def getVersionInfo(self, uuid, txn=None, open=False):

        versionSeq = self._versionSeq
        value = self._version.get(uuid._uuid, txn, self._flags, None)

        if value is None:
            raise AssertionError, 'version record is missing'

        versionId, format, schema = unpack('>16sll', value)
        if open:
            versionSeq.open(txn, versionId, DBSequence.DB_THREAD)
        version = versionSeq.last_value

        return UUID(versionId), version, format, schema
        
    def getVersion(self):

        return self._versionSeq.last_value

    def nextVersion(self):

        return self._versionSeq.get(self.store.txn)

    def purgeValue(self, txn, uuid):

        self.delete(uuid._uuid, txn)
        return 1

class HashTuple(tuple):

    def __contains__(self, name):

        if isinstance(name, unicode):
            name = name.encode('utf-8')

        return super(HashTuple, self).__contains__(_hash(name))

    def hash(self, name):

        return _hash(name)
