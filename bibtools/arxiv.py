# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Things having to do with arxiv.org.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import xml.etree.ElementTree as ET

from . import webutil as wu
from .bibcore import doi_to_maybe_bibcode

__all__ = ('autolearn_arxiv').split ()


_atom_ns = '{http://www.w3.org/2005/Atom}'
_arxiv_ns = '{http://arxiv.org/schemas/atom}'


def _translate_arxiv_name (auth):
    # XXX I assume that we don't get standardized names out of Arxiv, so
    # nontrivial last names will be gotten wrong. I don't see any point
    # in trying to solve this here.
    return auth.find (_atom_ns + 'name').text


def autolearn_arxiv (app, arxiv):
    url = 'http://export.arxiv.org/api/query?id_list=' + wu.urlquote (arxiv)
    info = {'arxiv': arxiv, 'keep': 0} # because we're autolearning

    # XXX sad to be not doing this incrementally, but Py 2.x doesn't
    # seem to have an incremental parser built in.

    print ('[Parsing', url, '...]')
    xmldoc = b''.join (wu.urlopen (url))
    root = ET.fromstring (xmldoc)
    ent = root.find (_atom_ns + 'entry')

    try:
        info['abstract'] = ent.find (_atom_ns + 'summary').text
    except:
        pass

    try:
        info['authors'] = [_translate_arxiv_name (a) for a in
                           ent.findall (_atom_ns + 'author')]
    except:
        pass

    try:
        info['doi'] = ent.find (_arxiv_ns + 'doi').text
    except:
        pass

    try:
        info['title'] = ent.find (_atom_ns + 'title').text
    except:
        pass

    try:
        info['year'] = int (ent.find (_atom_ns + 'published').text[:4])
    except:
        pass

    if 'doi' in info:
        info['bibcode'] = doi_to_maybe_bibcode (app, info['doi'])

    return info
