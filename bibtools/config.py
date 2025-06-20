# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Configuration subsystem
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import codecs
import configparser

from .util import bibpath, datastream, die

__all__ = ['BibConfig Error']


RCP = configparser.RawConfigParser
Error = configparser.Error


class BibConfig (RCP):
    def __init__ (self):
        super(BibConfig, self).__init__()
        self.read_file (codecs.getreader('utf-8')(datastream('defaults.cfg')))
        self.read (bibpath ('bib.cfg'))


    def get_or_die (self, section, option):
        try:
            return self.get (section, option)
        except Error:
            die ('cannot find required configuration key %s/%s', section, option)
