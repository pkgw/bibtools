# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Docstring!
"""

import codecs, json, os.path, re, sqlite3, sys, urllib2

from .util import *
from .config import BibConfig
from . import webutil as wu


class BibError (Exception):
    def __init__ (self, fmt, *args):
        if not len (args):
            self.bibmsg = str (fmt)
        else:
            self.bibmsg = fmt % args

    def __str__ (self):
        return self.bibmsg


class UsageError (BibError):
    pass

class PubLocateError (BibError):
    pass

class MultiplePubsError (PubLocateError):
    pass


def connect ():
    from .db import connect
    return connect ()


def get_proxy_or_die ():
    from .config import BibConfig
    from .proxy import get_proxy_or_die
    return get_proxy_or_die (BibConfig ())
