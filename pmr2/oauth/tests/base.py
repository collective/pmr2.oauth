import urllib
from time import time
from random import randint
from sys import maxint

from oauthlib.oauth1 import Client
from oauthlib.common import Request

import zope.interface
from zope.annotation.interfaces import IAttributeAnnotatable

from Testing import ZopeTestCase as ztc
from plone.session.tests.sessioncase import PloneSessionTestCase
from Zope2.App import zcml
from Products.Five import fiveconfigure
from Products.PloneTestCase import PloneTestCase as ptc
from Products.PloneTestCase.layer import PloneSite
from Products.PloneTestCase.layer import onsetup
from Products.PloneTestCase.layer import onteardown

import z3c.form.testing
from pmr2.oauth.plugins.oauth import OAuthPlugin

@onsetup
def setup():
    import pmr2.oauth
    fiveconfigure.debug_mode = True
    zcml.load_config('configure.zcml', pmr2.oauth)
    zcml.load_config('tests.zcml', pmr2.oauth.tests)
    fiveconfigure.debug_mode = False
    ztc.installPackage('pmr2.oauth')

@onteardown
def teardown():
    pass

setup()
teardown()
ptc.setupPloneSite(products=('pmr2.oauth',))


class OAuthTestCase(PloneSessionTestCase):

    def afterSetUp(self):
        PloneSessionTestCase.afterSetUp(self)
        self.app.folder = self.folder

        if self.folder.pas.hasObject("oauth"):
            self.app.folder.pas._delObject("oauth")

        self.app.folder.pas._setObject("oauth", OAuthPlugin("oauth"))


class IOAuthTestLayer(zope.interface.Interface):
    """\
    Mock layer
    """


def escape(s):
    return urllib.quote(s.encode('utf-8'), safe='~')


class TestRequest(z3c.form.testing.TestRequest):

    zope.interface.implements(IOAuthTestLayer, IAttributeAnnotatable)

    def __setitem__(self, key, value):
        self.form[key] = value

    def __getitem__(self, key):
        try:
            return super(TestRequest, self).__getitem__(key)
        except KeyError:
            return self.form[key]

    def __init__(self, oauth_keys=None, url=None, *a, **kw):
        super(TestRequest, self).__init__(*a, **kw)
        if url:
            parts = url.split('/')
            self._app_server = '/'.join(parts[:3])
            self._app_names = parts[3:]

        url = self.getURL()
        self.other = {}
        # Actual classes look for this
        self.other['ACTUAL_URL'] = url
        # Some other way of accessing this...
        self._environ['ACTUAL_URL'] = url

        if oauth_keys:
            self._auth = self.to_header(oauth_keys)

    def to_header(self, oauth_keys, realm=''):
        # copied from oauth2 (for now)
        oauth_params = ((k, v) for k, v in oauth_keys.items()
                            if k.startswith('oauth_'))
        stringy_params = ((k, escape(str(v))) for k, v in oauth_params)
        header_params = ('%s="%s"' % (k, v) for k, v in stringy_params)
        params_header = ', '.join(header_params)

        auth_header = 'OAuth realm="%s"' % realm
        if params_header:
            auth_header = "%s, %s" % (auth_header, params_header)

        return auth_header


def SignedTestRequest(form=None, consumer=None, token=None,
        url=None, callback=None, timestamp=None, verifier=None, *a, **kw):
    """\
    Creates a signed TestRequest
    """

    def safe_unicode(s):
        # I really really hate oauthlib's insistence on using unicode
        # on things that are really bytes.
        if isinstance(s, str):
            return unicode(s)

        return s

    if not consumer:
        raise ValueError('consumer must be provided to build a signed request')

    if form is None:
        form = {}

    result = TestRequest(form=form, *a, **kw)
    url = url or result.getURL()
    url = safe_unicode(url)
    method = safe_unicode(result.method)

    token_key = token and token.key
    token_secret = token and token.secret

    client = Client(
        safe_unicode(consumer.key),
        safe_unicode(consumer.secret),
        safe_unicode(token_key),
        safe_unicode(token_secret),
        safe_unicode(callback),
        verifier=safe_unicode(verifier),
    )

    # Manually sign this thing since we can't override timestamp
    # for our tests.
    request = Request(url, method)
    content_type = request.headers.get('Content-Type', None)
    request.oauth_params = client.get_oauth_params()

    # XXX assumptions here
    if timestamp:
        request.oauth_params[1] = (u'oauth_timestamp', safe_unicode(timestamp))

    request.oauth_params.append((u'oauth_signature', 
        client.get_oauth_signature(request)))

    url, headers, body = client._render(request, formencode=True, realm=None)

    result._auth = headers['Authorization']

    return result
