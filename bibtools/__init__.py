# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Global structure for the bibliography tool.
"""

__all__ = ('BibApp BibError PubLocateError MultiplePubsError').split ()


class BibError (Exception):
    def __init__ (self, fmt, *args):
        if not len (args):
            self.bibmsg = str (fmt)
        else:
            self.bibmsg = fmt % args

    def __str__ (self):
        return self.bibmsg


class PubLocateError (BibError):
    pass

class MultiplePubsError (PubLocateError):
    pass


class BibApp (object):
    _thedb = None
    _thecfg = None
    _theproxy = None

    @property
    def db (self):
        if self._thedb is None:
            from .db import connect
            self._thedb = connect ()
        return self._thedb


    @property
    def cfg (self):
        if self._thecfg is None:
            from .config import BibConfig
            self._thecfg = BibConfig ()
        return self._thecfg


    @property
    def proxy (self):
        if self._theproxy is None:
            from .proxy import get_proxy_or_die
            self._theproxy = get_proxy_or_die (self.cfg)
        return self._theproxy


    def __enter__ (self):
        return self


    def __exit__ (self, etype, evalue, etb):
        if self._thedb is not None:
            self._thedb.commit ()
            self._thedb.close ()
