# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Proxies.
"""

__all__ = ('get_proxy get_proxy_or_die').split ()

import cookielib, urllib2

from .util import *
from .webutil import *


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

    def __init__ (self, cfg, username, password):
        self.cj = cookielib.CookieJar ()
        self.opener = urllib2.build_opener (urllib2.HTTPRedirectHandler (),
                                            urllib2.HTTPCookieProcessor (self.cj))

        # XXX This doesn't quite belong here. We need it because otherwise
        # nature.com gives us the mobile site, which happens to not include
        # the easily-recognized <a> tag linking to the paper PDF. I don't know
        # exactly what's needed, but if we just send 'Mozilla/5.0' as the UA,
        # nature.com gives us a 500 error (!). So I've just copied my current
        # browser's UA.
        ua = cfg.get_or_die ('proxy', 'user-agent')
        self.opener.addheaders = [('User-Agent', ua)]

        self.inputs = list (self.default_inputs)
        self.inputs.append (('username', username))
        self.inputs.append (('password', password))


    def login (self, resp):
        # XXX we should verify the SSL cert of the counterparty, lest we send
        # our password to malicious people.
        parser = parse_http_html (resp, HarvardProxyLoginParser ())

        if parser.formurl is None:
            die ('malformed proxy page response?')

        from urlparse import urljoin
        posturl = urljoin (resp.url, parser.formurl)
        values = {}

        for name, value in parser.inputs:
            values[name] = value

        for name, value in self.inputs:
            values[name] = value

        from urllib import urlencode # yay terrible Python APIs
        req = urllib2.Request (posturl, urlencode (values))
        # The response will redirect to the original target page.
        return self.opener.open (req)


    def open (self, url):
        from urlparse import urlparse, urlunparse
        scheme, loc, path, params, query, frag = urlparse (url)

        if loc.endswith ('arxiv.org'):
            # For whatever reason, the proxy server doesn't work
            # if we try to access Arxiv with it.
            proxyurl = url
        else:
            loc += self.suffix
            proxyurl = urlunparse ((scheme, loc, path, params, query, frag))

        resp = self.opener.open (proxyurl)

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

        from urlparse import urlparse, urlunparse

        scheme, loc, path, params, query, frag = urlparse (url)
        if not loc.endswith (self.suffix):
            return url

        loc = loc[:-len (self.suffix)]
        return urlunparse ((scheme, loc, path, params, query, frag))


def get_proxy (cfg):
    # TODO: return some kind of null proxy if nothing configured. Then
    # we can kill get_proxy_or_die.

    from .secret import load_user_secret
    from .config import Error

    try:
        kind = cfg.get ('proxy', 'kind')
        username = cfg.get ('proxy', 'username')
    except Error:
        return None

    # It's not good to have this hanging around in memory, but Python
    # strings are immutable and we have no idea what (if anything) `del
    # password` would accomplish, so I don't think we can really do
    # better.
    password = load_user_secret (cfg)

    if kind == 'harvard':
        return HarvardProxy (cfg, username, password)

    die ('don\'t recognize proxy kind "%s"', kind)


def get_proxy_or_die (cfg):
    proxy = get_proxy (cfg)
    if proxy is None:
        die ('no fulltext-access proxy is configured')
    return proxy
