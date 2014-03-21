# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
BibTeX-related stuff.

TODO: styles defined in a support file or something.

"""

__all__ = ('bibtexify_one export_to_bibtex write_bibtexified').split ()

import json, sys

from .util import *
from .unicode_to_latex import unicode_to_latex


# Import (TODO: move over all the ingest-related stuff)

def _translate_bibtex_name (name):
    # generically: von Foo, Jr, Bob C. ; citeulike always gives us comma form
    a = [i.strip () for i in name.split (',')]

    if len (a) == 0:
        warn ('all last name, I think: %s', name)
        return a.replace (' ', '_')

    first = a[-1]
    surname = (',_'.join (a[:-1])).replace (' ', '_')

    if not len (first):
        warn ('CiteULike mis-parsed name, I think: %s', name)

    return first + ' ' + surname


# Export

class BibtexStyleBase (object):
    include_doi = True
    include_title = False
    issn_name_map = None
    normalize_pages = False


class ApjBibtexStyle (BibtexStyleBase):
    normalize_pages = True

    def __init__ (self):
        inm = {}

        for line in datastream ('apj-issnmap.txt'):
            line = line.split ('#')[0].strip ().decode ('utf-8')
            if not len (line):
                continue

            issn, jname = line.split (None, 1)
            inm[issn] = unicode_to_latex (jname)

        self.issn_name_map = inm


bibtex_styles = {'apj': ApjBibtexStyle}


def bibtexify_name (style, name):
    given, family = name

    fbits = family.rsplit (',', 1)

    if len (fbits) > 1:
        return '{%s}, %s, %s' % (unicode_to_latex (fbits[0]),
                                 unicode_to_latex (fbits[1]),
                                 unicode_to_latex (given))

    return '{%s}, %s' % (unicode_to_latex (fbits[0]),
                         unicode_to_latex (given))


def bibtexify_names (style, names):
    return ' and '.join (bibtexify_name (style, n) for n in names)


def bibtexify_one (db, style, pub):
    """Returns a dict in which the values are already latex-encoded.
    '_type' is the bibtex type, '_ident' is the bibtex identifier."""

    rd = json.loads (pub.refdata)

    for k in rd.keys ():
        rd[k] = unicode_to_latex (rd[k])

    names = list (db.get_pub_authors (pub.id, 'author'))
    if len (names):
        rd['author'] = bibtexify_names (style, names)

    names = list (db.get_pub_authors (pub.id, 'editor'))
    if len (names):
        rd['editor'] = bibtexify_names (style, names)

    if style.include_doi and pub.doi is not None:
        rd['doi'] = unicode_to_latex (pub.doi)

    if style.issn_name_map is not None and 'issn' in rd:
        ltxjname = style.issn_name_map.get (rd['issn'])
        if ltxjname is not None:
            rd['journal'] = ltxjname

    if style.normalize_pages and 'pages' in rd:
        p = rd['pages'].split ('--')[0]
        if p[-1] == '+':
            p = p[:-1]
        rd['pages'] = p

    if style.include_title and pub.title is not None:
        rd['title'] = unicode_to_latex (pub.title)

    if pub.year is not None:
        rd['year'] = str (pub.year)


    return rd


def write_bibtexified (write, btdata):
    """This will mutate `btdata`."""

    bttype = btdata.pop ('_type')
    btid = btdata.pop ('_ident')

    write ('@')
    write (bttype)
    write ('{')
    write (btid)

    for k in sorted (btdata.iterkeys ()):
        write (',\n  ')
        write (k)
        write (' = {')
        write (btdata[k])
        write ('}')

    write ('\n}\n')


def export_to_bibtex (app, style, citednicks, write=None):
    if write is None:
        write = sys.stdout.write

    seenids = {}
    first = True

    for nick in sorted (citednicks):
        curs = app.db.pub_fquery ('SELECT p.* FROM pubs AS p, nicknames AS n '
                                  'WHERE p.id == n.pubid AND n.nickname == ?', nick)
        res = list (curs)

        if not len (res):
            die ('citation to unrecognized nickname "%s"', nick)
        if len (res) != 1:
            die ('cant-happen multiple matches for nickname "%s"', nick)

        pub = res[0]

        if pub.id in seenids:
            die ('"%s" and "%s" refer to the same publication; this will '
                 'cause duplicate entries', nick, seenids[pub.id])

        if pub.refdata is None:
            die ('no reference data for "%s"', nick)

        seenids[pub.id] = nick

        if first:
            first = False
        else:
            write ('\n')

        bt = bibtexify_one (app.db, style, pub)
        bt['_ident'] = nick
        write_bibtexified (write, bt)
