# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Various utilities for HTTP-related activities.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import codecs
import six

try:
    from http import cookiejar
except ImportError:
    import cookielib as cookiejar

try:
    from urllib import error, parse, request
except ImportError:
    import urrlib2 as error
    import urrlib2 as parse
    import urrlib2 as request

from .util import *

__all__ = str('''
HTMLParser
HTTPError
build_opener
get_url_from_redirection
parse_http_html
urlencode
urljoin
urlopen
urlparse
urlquote
urlunparse
urlunquote
''').split ()


build_opener = request.build_opener
urlencode = parse.urlencode
HTTPError = error.HTTPError
urlquote = parse.quote
urlunquote = parse.unquote
urlopen = request.urlopen

try:
    from urllib.parse import urljoin, urlparse, urlunparse
except ImportError:
    from urlparse import urljoin, urlparse, urlunparse

try:
    # renamed in Python 3.
    from html.parser import HTMLParser
except ImportError:
    from HTMLParser import HTMLParser


class NonRedirectingProcessor (request.HTTPErrorProcessor):
    # Copied from StackOverflow q 554446.
    def http_response (self, request, response):
        return response

    https_response = http_response


class DebugRedirectHandler (request.HTTPRedirectHandler):
    """Shouldn't be used in production code, but useful for proxy debugging."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        import sys
        print ('REDIRECT:', req.get_method (), code, newurl, file=sys.stderr)
        return request.HTTPRedirectHandler.redirect_request (self, req, fp, code, msg, headers, newurl)


def get_url_from_redirection (url):
    """Note that we don't go through the proxy class here for convenience, under
    the assumption that all of these redirections involve public information
    that won't require privileged access."""

    opener = request.build_opener (NonRedirectingProcessor ())
    resp = opener.open (url)

    if resp.code not in (301, 302, 303, 307) or 'Location' not in resp.headers:
        die ('expected a redirection response for URL %s but didn\'t get one', url)

    resp.close ()
    return resp.headers['Location']


def parse_http_html (resp, parser):
    """`parser` need only have two methods: `feed()` and `close()`."""

    debug = False # XXX hack

    if six.PY2:
        charset = resp.headers.getparam ('charset')
    else:
        charset = resp.headers.get_content_charset('ISO-8859-1')

    if charset is None:
        charset = 'ISO-8859-1'

    dec = codecs.getincrementaldecoder (charset) ()

    if debug:
        f = open ('debug.html', 'w')

    while True:
        d = resp.read (4096)
        if not len (d):
            text = dec.decode (b'', final=True)
            parser.feed (text)
            break

        if debug:
            f.write (d)

        text = dec.decode (d)
        parser.feed (text)

    if debug:
        f.close ()

    resp.close ()
    parser.close ()
    return parser
