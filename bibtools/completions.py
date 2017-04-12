# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Tab-completion helpers. Because we're classy.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from .util import *


try:
    from string import ascii_lowercase as string_letters
except ImportError:
    from string import letters as string_letters


def process (app, tool, subcommand, args):
    func = globals ().get ('complete_' + subcommand)
    if not callable (func):
        die ('unrecognized completion subcommand "%s"', subcommand)

    func (app, tool, args)


def stem_compatible (stem, partial):
    i = 0
    n = min (len (stem), len (partial))

    while i < n:
        if partial[i] != stem[i]:
            return False
        i += 1

    return True


def complete_commands (app, tool, args):
    for cname in tool.commands.keys ():
        print (cname)


def _complete_pub_common (app, args, is_multi):
    import string

    if not len (args) or not len (args[0]):
        # No partial; let's not try to yield every possible thing
        for c in string_letters:
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

    if partial[0] in string_letters:
        print_nfasys (app, partial, is_multi)

    print_arxivs (app, partial)
    print_nicknames (app, partial)
    # TODO: percent IDs; "doi:...", "arxiv:..."


def complete_pub (app, tool, args):
    _complete_pub_common (app, args, False)

def complete_multipub (app, tool, args):
    _complete_pub_common (app, args, True)


def print_dois (app, partial):
    for tup in app.db.execute ('SELECT doi FROM pubs WHERE '
                               'doi LIKE ?', (partial + '%', )):
        print (tup[0])


def print_bibcodes (app, partial):
    for tup in app.db.execute ('SELECT bibcode FROM pubs WHERE '
                               'bibcode LIKE ?', (partial + '%', )):
        print (tup[0])


def print_nfasys (app, partial, is_multi):
    # Case where the year hasn't yet been provided
    if is_multi:
        for tup in app.db.execute ('SELECT DISTINCT nfas FROM pubs WHERE '
                                   'nfas LIKE ?', (partial + '%', )):
            print (tup[0] + '.*')

    for tup in app.db.execute ('SELECT DISTINCT nfas, year FROM pubs WHERE '
                               'nfas LIKE ?', (partial + '%', )):
        print (tup[0] + '.' + str (tup[1]))

    if '.' in partial:
        # Maybe a partial year has been provided?
        nfas = partial.rsplit ('.', 1)[0]
        need_print_star = is_multi

        for tup in app.db.execute ('SELECT DISTINCT year FROM pubs WHERE '
                                   'nfas == ?', (nfas, )):
            if need_print_star:
                print (nfas + '.*')
                need_print_star = False
            print (nfas + '.' + str (tup[0]))


def print_arxivs (app, partial):
    for tup in app.db.execute ('SELECT arxiv FROM pubs WHERE '
                               'arxiv LIKE ?', (partial + '%', )):
        print (tup[0])


def print_nicknames (app, partial):
    for tup in app.db.execute ('SELECT nickname FROM nicknames WHERE '
                               'nickname LIKE ?', (partial + '%', )):
        print (tup[0])


def complete_group_subcmds (app, tool, args):
    # Hmmmm could genericize this ...
    for cname in tool.commands['group'].commands:
        print (cname)


def complete_group (app, tool, args):
    if not len (args) or not len (args[0]):
        # No partial to work with.
        for tup in app.db.execute ('SELECT DISTINCT name FROM publists WHERE '
                                   'name LIKE "user_%"'):
            print (tup[0][5:])
        return

    partial = args[0]

    for tup in app.db.execute ('SELECT DISTINCT name FROM publists WHERE '
                               'name LIKE ?', ('user_' + partial + '%', )):
        print (tup[0][5:])
