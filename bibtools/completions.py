# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Tab-completion helpers. Because we're classy.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
from .util import *


def process (app, subcommand, args):
    func = globals ().get ('complete_' + subcommand)
    if not callable (func):
        die ('unrecognized completion subcommand "%s"', subcommand)

    func (app, args)


def stem_compatible (stem, partial):
    i = 0
    n = min (len (stem), len (partial))

    while i < n:
        if partial[i] != stem[i]:
            return False
        i += 1

    return True


def complete_commands (app, args):
    from . import cli

    for item in dir (cli):
        if not item.startswith ('cmd_'):
            continue
        print (item[4:])


def complete_pub (app, args):
    import string

    if not len (args) or not len (args[0]):
        # No partial; let's not try to yield every possible thing
        for c in string.letters:
            print (c)
        for c in string.digits:
            print (c)
        print ('%')
        return

    partial = args[0]

    if stem_compatible ('10.', partial):
        print_dois (app, partial)

    if stem_compatible ('1', partial) or stem_compatible ('20', partial):
        print_bibcodes (app, partial)

    if partial[0] in string.letters:
        print_nfasys (app, partial)

    print_arxivs (app, partial)
    print_nicknames (app, partial)
    # TODO: percent IDs; "doi:...", "arxiv:..."


def print_dois (app, partial):
    for tup in app.db.execute ('SELECT doi FROM pubs WHERE '
                               'doi LIKE ?', (partial + '%', )):
        print (tup[0])


def print_bibcodes (app, partial):
    for tup in app.db.execute ('SELECT bibcode FROM pubs WHERE '
                               'bibcode LIKE ?', (partial + '%', )):
        print (tup[0])


def print_nfasys (app, partial):
    if '.' not in partial:
        for tup in app.db.execute ('SELECT DISTINCT nfas, year FROM pubs WHERE '
                                   'nfas LIKE ?', (partial + '%', )):
            print (tup[0] + '.' + str (tup[1]))
        return

    nfas = partial.rsplit ('.', 1)[0]

    for tup in app.db.execute ('SELECT DISTINCT year FROM pubs WHERE '
                               'nfas == ?', (nfas, )):
        print (nfas + '.' + str (tup[0]))


def print_arxivs (app, partial):
    for tup in app.db.execute ('SELECT arxiv FROM pubs WHERE '
                               'arxiv LIKE ?', (partial + '%', )):
        print (tup[0])


def print_nicknames (app, partial):
    for tup in app.db.execute ('SELECT nickname FROM nicknames WHERE '
                               'nickname LIKE ?', (partial + '%', )):
        print (tup[0])
