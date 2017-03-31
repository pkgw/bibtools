# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Configuration subsystem
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import codecs
try:
    # module renamed to this in Python 3.
    import configparser
except ImportError:
    import ConfigParser as configparser

from .util import bibpath, datastream, die

__all__ = ['BibConfig Error']


RCP = configparser.RawConfigParser
Error = configparser.Error


class BibConfig (RCP):
    def __init__ (self):
        # stupid old-style classes can't use super()
        RCP.__init__ (self)
        self.readfp (codecs.getreader('utf-8')(datastream('defaults.cfg')))
        self.read (bibpath ('bib.cfg'))


    def get_or_die (self, section, option):
        try:
            return self.get (section, option)
        except Error:
            die ('cannot find required configuration key %s/%s', section, option)
