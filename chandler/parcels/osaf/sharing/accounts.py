#   Copyright (c) 2003-2007 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

__all__ = [
    'SharingAccount',
    'WebDAVAccount',
    'Proxy',
    'getProxy',
    'getProxies',
]

from application import schema
from osaf import pim
import conduits, utility
import logging
import urlparse
from osaf.framework.password import passwordAttribute, Password
from osaf.framework.twisted import waitForDeferred


logger = logging.getLogger(__name__)

class SharingAccount(pim.ContentItem):

    username = schema.One(
        schema.Text, initialValue = u'',
    )

    password = passwordAttribute

    host = schema.One(
        schema.Text,
        doc = 'The hostname of the account',
        initialValue = u'',
    )
    path = schema.One(
        schema.Text,
        doc = 'Base path on the host to use for publishing',
        initialValue = u'',
    )
    port = schema.One(
        schema.Integer,
        doc = 'The non-SSL port number to use',
        initialValue = 80,
    )
    useSSL = schema.One(
        schema.Boolean,
        doc = 'Whether or not to use SSL/TLS',
        initialValue = False,
    )

    accountProtocol = schema.One(
        initialValue = '',
    )

    accountType = schema.One(
        initialValue = '',
    )

    conduits = schema.Sequence(
        conduits.HTTPMixin,
        inverse=conduits.HTTPMixin.account
    )

    def getLocation(self):
        """
        Return the base url of the account
        """

        if self.useSSL:
            scheme = "https"
            defaultPort = 443
        else:
            scheme = "http"
            defaultPort = 80

        if self.port == defaultPort:
            url = "%s://%s" % (scheme, self.host)
        else:
            url = "%s://%s:%d" % (scheme, self.host, self.port)

        sharePath = self.path.strip("/")
        url = urlparse.urljoin(url, sharePath + "/")
        return url

    @classmethod
    def findMatchingAccount(cls, view, url):
        """
        Find a Sharing account which corresponds to a URL.

        The url being passed in is for a collection -- it will include the
        collection name in the url.  We need to find a webdav account who
        has been set up to operate on the parent directory of this collection.
        For example, if the url is http://pilikia.osafoundation.org/dev1/foo/
        we need to find an account whose schema+host+port match and whose path
        starts with /dev1

        Note: this logic assumes only one account will match; you aren't
        currently allowed to have to multiple webdav accounts pointing to the
        same scheme+host+port+path combination.

        @param view: The repository view object
        @type view: L{repository.persistence.RepositoryView}
        @param url: The url which points to a collection
        @type url: String
        @return: An account item, or None if no WebDAV account could be found.
        """

        (scheme, useSSL, host, port, path, query, fragment, ticket, parentPath,
            shareName) = utility.splitUrl(url)

        # Get the parent directory of the given path:
        # '/dev1/foo/bar' becomes ['dev1', 'foo']
        path = path.strip('/').split('/')[:-1]
        # ['dev1', 'foo'] becomes "dev1/foo"
        path = "/".join(path)

        for account in cls.iterItems(view):
            # Does this account's url info match?
            accountPath = account.path.strip('/')
            if (account.isSetUp() and
                account.useSSL == useSSL and
                account.host == host and
                account.port == port and
                path.startswith(accountPath)):
                return account

        return None

    def isSetUp(self):
        return bool(self.host and self.username)

class WebDAVAccount(SharingAccount):

    accountProtocol = schema.One(
        initialValue = 'WebDAV',
    )

    accountType = schema.One(
        initialValue = 'SHARING_DAV',
    )






class Proxy(schema.Item):
    host = schema.One(schema.Text, defaultValue = u'')
    port = schema.One(schema.Integer, defaultValue = 8080)
    protocol = schema.One(schema.Text, defaultValue = u'HTTP')
    useAuth = schema.One(schema.Boolean, defaultValue = False)
    username = schema.One(schema.Text, defaultValue = u'')
    password = passwordAttribute
    active = schema.One(schema.Boolean, defaultValue = False)
    bypass = schema.One(schema.Text, defaultValue = u'localhost, .local, 127.0.0.1')

    def getPasswd(self):
        pw = getattr(self, "password", None)
        if pw is None:
            return ""
        else:
            return waitForDeferred(pw.decryptPassword())

    def setPasswd(self, text):
        pw = getattr(self, "password", None)
        if pw is None:
            if text is None:
                return
            pw = Password(itsParent=self)
            self.password = pw
        waitForDeferred(pw.encryptPassword(text))

    def delPasswd(self):
        if hasattr(self, "password"):
            pw = self.password
            if pw is not None:
                pw.Delete(recursive=True)
            del self.password

    # use 'proxy.passwd' for convenience.  I would have named this property
    # 'password', but Password.holders seems to require 'password' to be a
    # persistent attribute.
    passwd = property(getPasswd, setPasswd, delPasswd)

    def appliesTo(self, host):
        if not self.bypass:
            return True # not bypassing anything

        host = host.lower()
        for s in self.bypass.lower().split(','):
            if s:
                s = s.strip()
                if s[0].isalpha() or s[0] == '.': # hostname/domain
                    if host.endswith(s):
                        return False # a match; we're not proxying this host
                else: # IP address
                    if host.startswith(s):
                        return False # a match; we're not proxying this host

        return True


def getProxy(rv, protocol=u'HTTP'):
    for proxy in Proxy.iterItems(rv):
        if proxy.protocol == protocol:
            return proxy
    return Proxy(itsView=rv, protocol=protocol, active=False)

def getProxies(rv):
    return list(Proxy.iterItems(rv))
