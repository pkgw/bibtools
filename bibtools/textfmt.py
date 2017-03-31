# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Import/export from our text format.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
from six import text_type

import json

from .util import *
from .bibcore import *

__all__ = ('export_one import_one').split ()


def export_one (app, pub, stream, width):
    write = stream.write

    # Title and year
    if pub.title is None:
        write ('--no title--\n')
    else:
        print_linewrapped (pub.title, width=width, stream=stream)
    if pub.year is None:
        write ('--no year--\n')
    else:
        write (text_type (pub.year))
        write ('\n')
    write ('\n')

    # Unique identifiers
    write ('arxiv = ')
    write (pub.arxiv or '')
    write ('\n')
    write ('bibcode = ')
    write (pub.bibcode or '')
    write ('\n')
    write ('doi = ')
    write (pub.doi or '')
    write ('\n')
    for (nick, ) in app.db.execute ('SELECT nickname FROM nicknames WHERE pubid == ? '
                                    'ORDER BY nickname asc', (pub.id, )):
        write ('nick = ')
        write (nick)
        write ('\n')
    write ('\n')

    # Authors
    anyauth = False
    for given, family in app.db.get_pub_authors (pub.id, 'author'):
        write (encode_name (given, family))
        write ('\n')
        anyauth = True
    if not anyauth:
        write ('--no authors--\n')
    firsteditor = True
    for given, family in app.db.get_pub_authors (pub.id, 'editor'):
        if firsteditor:
            write ('--editors--\n')
            firsteditor = False
        write (encode_name (given, family))
        write ('\n')
    write ('\n')

    # Reference info
    if pub.refdata is None:
        write ('--no reference data--\n')
    else:
        rd = json.loads (pub.refdata)

        btype = rd.pop ('_type')
        write ('@')
        write (btype)
        write ('\n')

        for k in sorted (rd.keys ()):
            write (k)
            write (' = ')
            write (rd[k])
            write ('\n')
    write ('\n')

    # Abstract
    if pub.abstract is None:
        write ('--no abstract--\n')
    else:
        print_linewrapped (pub.abstract, width=width, stream=stream, maxwidth=72)
    write ('\n')

    # TODO: notes, lists


def _import_get_chunk (stream, gotoend=False):
    lines = []

    for line in stream:
        line = line.strip ()

        if not len (line) and not gotoend:
            return lines

        lines.append (line)

    while len (lines) and not len (lines[-1]):
        lines = lines[:-1]

    return lines


def import_one (stream):
    info = {}

    # title / year
    c = _import_get_chunk (stream)

    if len (c) < 2:
        die ('title/year chunk must contain at least two lines')

    info['title'] = squish_spaces (' '.join (c[:-1]))
    if info['title'].startswith ('--'):
        del info['title']

    if not c[-1].startswith ('--'):
        try:
            info['year'] = int (c[-1])
        except Exception as e:
            die ('publication year must be an integer or "--no year--"; '
                 'got "%s"', c[-1])

    # identifiers
    c = _import_get_chunk (stream)
    info['nicknames'] = []

    for line in c:
        if '=' not in line:
            die ('identifier lines must contain "=" signs; got "%s"', line)
        k, v = line.split ('=', 1)
        k = k.strip ()
        v = v.strip ()

        if not v:
            continue

        if k == 'arxiv':
            info['arxiv'] = v
        elif k == 'bibcode':
            info['bibcode'] = v
        elif k == 'doi':
            info['doi'] = v
        elif k == 'nick':
            info['nicknames'].append (v)
        else:
            die ('unexpected identifier kind "%s"', k)

    # authors
    c = _import_get_chunk (stream)
    namelist = info['authors'] = []

    for line in c:
        # This "--" flag must be exact for --editors-- to work
        if line == '--no authors--':
            pass
        elif line == '--editors--':
            namelist = info['editors'] = []
        else:
            namelist.append (line)

    # reference data
    c = _import_get_chunk (stream)

    if not c[0].startswith ('--'):
        rd = info['refdata'] = {}

        if c[0][0] != '@':
            die ('reference data chunk must begin with an "@"; got "%s"', c[0])
        rd['_type'] = c[0][1:]

        for line in c[1:]:
            if '=' not in line:
                die ('ref data lines must contain "=" signs; got "%s"', line)
            k, v = line.split ('=', 1)
            k = k.strip ()
            v = v.strip ()
            rd[k] = v

    # abstract
    c = _import_get_chunk (stream, gotoend=True)
    abs = ''
    spacer = ''

    for line in c:
        if not len (line):
            spacer = '\n'
        elif line == '--no abstract--':
            pass # exact match here too; legitimate lines could start with '--'
        else:
            abs += spacer + line
            spacer = ' '

    if len (abs):
        info['abstract'] = abs

    return info
