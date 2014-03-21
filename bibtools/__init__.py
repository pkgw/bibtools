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


def _translate_unixref_name (personelem):
    # XXX: deal with "The Fermi-LAT Collaboration", "Gopal-Krishna", etc.

    given = personelem.find ('given_name').text
    sur = personelem.find ('surname').text
    return given + ' ' + sur.replace (' ', '_')


def _translate_arxiv_name (auth):
    # XXX I assume that we don't get standardized names out of Arxiv, so
    # nontrivial last names will be gotten wrong. I don't see any point
    # in trying to solve this here.
    return auth.find (_atom_ns + 'name').text


def autolearn_doi (doi):
    # TODO: editors. See e.g. unixref output for 10.1007/978-3-642-14335-9_1
    # -- three <contributors> sections (!), with contributor_role="editor" on
    # the <person_name> element.

    import xml.etree.ElementTree as ET

    # XXX loading config scattershot as-needed isn't ideal ...
    apikey = BibConfig ().get_or_die ('api-keys', 'crossref')

    url = ('http://crossref.org/openurl/?id=%s&noredirect=true&pid=%s&'
           'format=unixref' % (urlquote (doi), urlquote (apikey)))
    info = {'doi': doi, 'keep': 0} # because we're autolearning

    # XXX sad to be not doing this incrementally, but Py 2.x doesn't
    # seem to have an incremental parser built in.

    print '[Parsing', url, '...]'
    xmldoc = ''.join (urllib2.urlopen (url))
    root = ET.fromstring (xmldoc)

    jelem = root.find ('doi_record/crossref/journal')
    if jelem is None:
        die ('no <journal> element as expected in UnixRef XML for %s', doi)

    try:
        info['authors'] = [_translate_unixref_name (p) for p in
                           jelem.findall ('journal_article/contributors/person_name')]
    except:
        pass

    try:
        info['title'] = ' '.join (t.strip () for t in
                                  jelem.find ('journal_article/titles/title').itertext ())
    except:
        pass

    try:
        info['year'] = int (jelem.find ('journal_issue/publication_date/year').text)
    except:
        pass

    return info


_atom_ns = '{http://www.w3.org/2005/Atom}'
_arxiv_ns = '{http://arxiv.org/schemas/atom}'


def autolearn_arxiv (arxiv):
    import xml.etree.ElementTree as ET

    url = 'http://export.arxiv.org/api/query?id_list=' + urlquote (arxiv)
    info = {'arxiv': arxiv, 'keep': 0} # because we're autolearning

    # XXX sad to be not doing this incrementally, but Py 2.x doesn't
    # seem to have an incremental parser built in.

    print '[Parsing', url, '...]'
    xmldoc = ''.join (urllib2.urlopen (url))
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
        info['bibcode'] = doi_to_maybe_bibcode (info['doi'])

    return info


