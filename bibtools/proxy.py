# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Proxies.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import cookielib, urllib2

from .util import *
from .webutil import *

__all__ = ('get_proxy').split ()


class HarvardProxyLoginParser (HTMLParser):
    def __init__ (self):
        HTMLParser.__init__ (self)
        self.formurl = None
        self.inputs = []


    def handle_starttag (self, tag, attrs):
        if tag == 'form':
            attrs = dict (attrs)
            self.formurl = attrs.get ('action')
            if attrs.get ('method') != 'post':
                die ('unexpected form method')
        elif tag == 'input':
            attrs = dict (attrs)
            if 'name' not in attrs or 'value' not in attrs:
                die ('missing form input information')
            self.inputs.append ((attrs['name'], attrs['value']))


class HarvardProxy (object):
    suffix = '.ezp-prod1.hul.harvard.edu'
    loginurl = 'https://www.pin1.harvard.edu/cas/login'
    forwardurl = 'http://ezp-prod1.hul.harvard.edu/connect'

    default_inputs = [
        ('compositeAuthenticationSourceType', 'PIN'),
    ]

    def __init__ (self, user_agent, username, password):
        self.cj = cookielib.CookieJar ()

        # Older articles in Wiley's Online Library hit the default limit of 10
        # redirections.
        rh = urllib2.HTTPRedirectHandler ()
        rh.max_redirections = 20
        self.opener = urllib2.build_opener (rh,
                                            urllib2.HTTPCookieProcessor (self.cj))
        self.opener.addheaders = [('User-Agent', user_agent)]

        self.inputs = list (self.default_inputs)
        self.inputs.append (('username', username))
        self.inputs.append (('password', password))


    def login (self, resp):
        # XXX we should verify the SSL cert of the counterparty, lest we send
        # our password to malicious people.
        parser = parse_http_html (resp, HarvardProxyLoginParser ())

        if parser.formurl is None:
            die ('malformed proxy page response?')

        posturl = urljoin (resp.url, parser.formurl)
        values = {}

        for name, value in parser.inputs:
            values[name] = value

        for name, value in self.inputs:
            values[name] = value

        req = urllib2.Request (posturl, urlencode (values))
        # The response will redirect to the original target page.
        return self.opener.open (req)


    def open (self, url):
        scheme, loc, path, params, query, frag = urlparse (url)
        proxyurl = urlunparse ((scheme, loc + self.suffix, path,
                                params, query, frag))

        try:
            resp = self.opener.open (proxyurl)
        except urllib2.HTTPError as e:
            if e.code == 404:
                # The proxy doesn't feel like proxying this URL. Try just
                # accessing it directly.
                return self.opener.open (url)
            raise e

        if resp.url.startswith (self.loginurl):
            resp = self.login (resp)

        if resp.url.startswith (self.forwardurl):
            # Sometimes we get forwarded to a separate cookie-setting page
            # that requires us to re-request the original URL.
            resp = self.opener.open (proxyurl)

        return resp


    def unmangle (self, url):
        if url is None:
            return None # convenience

        scheme, loc, path, params, query, frag = urlparse (url)
        if not loc.endswith (self.suffix):
            return url

        loc = loc[:-len (self.suffix)]
        return urlunparse ((scheme, loc, path, params, query, frag))


class NullProxy (object):
    def __init__ (self, user_agent):
        pass # XXX we should honor user_agent; see below.

    def open (self, url):
        return urlopen (url)

    def unmangle (self, url):
        return url


def get_proxy (cfg):
    from .secret import load_user_secret
    from .config import Error

    try:
        kind = cfg.get ('proxy', 'kind')
        username = cfg.get ('proxy', 'username')
    except Error:
        kind = None

    # This is awkward. All proxies have to be able to send a User-Agent that
    # we specify. This is because otherwise nature.com gives us its mobile
    # site, which happens to not include the easily-recognized <a> tag linking
    # to the paper PDF. I don't know exactly what's needed, but if we just
    # send 'Mozilla/5.0' as the UA, nature.com gives us a 500 error (!). So
    # I've just copied my current browser's UA.
    ua = cfg.get_or_die ('proxy', 'user-agent')

    # It's not good to have the password hanging around in memory, but Python
    # strings are immutable and we have no idea what (if anything) `del
    # password` would accomplish, so I don't think we can really do better.

    if kind == 'harvard':
        password = load_user_secret (cfg)
        return HarvardProxy (ua, username, password)

    warn ('no proxy defined; will likely have trouble obtaining full-text articles')
    return NullProxy (ua)
