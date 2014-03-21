# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Configuration subsystem
"""

__all__ = ['BibConfig']

try:
    # module renamed to this in Python 3.
    import configparser
except ImportError:
    import ConfigParser as configparser

from .util import bibpath, datastream, die

RCP = configparser.RawConfigParser


class BibConfig (RCP):
    def __init__ (self):
        # stupid old-style classes can't use super()
        RCP.__init__ (self)
        self.readfp (datastream ('defaults.cfg'))
        self.read (bibpath ('bib.cfg'))


    def get_or_die (self, section, option):
        try:
            return self.get (section, option)
        except configparser.Error:
            die ('cannot find required configuration key %s/%s', section, option)


    def get_proxy (self):
        # TODO: return some kind of null proxy if nothing configured. Then
        # we can kill get_proxy_or_die.

        from .secret import load_user_secret

        try:
            kind = self.get ('proxy', 'kind')
            username = self.get ('proxy', 'username')
        except configparser.Error:
            return None

        # It's not good to have this hanging around in memory, but Python
        # strings are immutable and we have no idea what (if anything) `del
        # password` would accomplish, so I don't think we can really do
        # better.
        password = load_user_secret ()

        if kind == 'harvard':
            from . import HarvardProxy
            return HarvardProxy (username, password)

        die ('don\'t recognize proxy kind "%s"', kind)


    def get_proxy_or_die (self):
        proxy = self.get_proxy ()
        if proxy is None:
            die ('no fulltext-access proxy is configured')
        return proxy
