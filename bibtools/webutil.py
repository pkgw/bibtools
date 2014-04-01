# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Various utilities for HTTP-related activities.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import codecs, cookielib, urllib, urllib2

from .util import *

__all__ = ('HTMLParser HTTPError get_url_from_redirection parse_http_html '
           'urlencode urljoin urlopen urlparse urlquote urlunparse urlunquote').split ()


urlencode = urllib.urlencode
HTTPError = urllib2.HTTPError
urlquote = urllib2.quote
urlunquote = urllib2.unquote
urlopen = urllib2.urlopen
from urlparse import urljoin, urlparse, urlunparse

try:
    # renamed in Python 3.
    from html.parser import HTMLParser
except ImportError:
    from HTMLParser import HTMLParser


class NonRedirectingProcessor (urllib2.HTTPErrorProcessor):
    # Copied from StackOverflow q 554446.
    def http_response (self, request, response):
        return response

    https_response = http_response


def get_url_from_redirection (url):
    """Note that we don't go through the proxy class here for convenience, under
    the assumption that all of these redirections involve public information
    that won't require privileged access."""

    opener = urllib2.build_opener (NonRedirectingProcessor ())
    resp = opener.open (url)

    if resp.code not in (301, 302, 303, 307) or 'Location' not in resp.headers:
        die ('expected a redirection response for URL %s but didn\'t get one', url)

    resp.close ()
    return resp.headers['Location']


def parse_http_html (resp, parser):
    """`parser` need only have two methods: `feed()` and `close()`."""

    debug = False # XXX hack

    charset = resp.headers.getparam ('charset')
    if charset is None:
        charset = 'ISO-8859-1'

    dec = codecs.getincrementaldecoder (charset) ()

    if debug:
        f = open ('debug.html', 'w')

    while True:
        d = resp.read (4096)
        if not len (d):
            text = dec.decode ('', final=True)
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
