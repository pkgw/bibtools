# -*- mode: python; coding: utf-8 -*-
# Copyright 2014, 2016 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""Core bibliographic routines.

Generic things dealing with names, identifiers, etc.

We store names like so:
  "Albert J. von_Trapp_Rodolfo,_Jr."
As far as I can see, this makes it easy to pull out surnames and deal with all
that mess. We're pretty boned once I start dealing with papers whose have
author names given in both Latin and Chinese characters, though.

Another thing to be wary of is "names" like "The Fermi-LAT Collaboration".
Some Indians have only single names (e.g. "Gopal-Krishna").

NFAS = normalized first-author surname. We decapitalize, remove accents, and
replace nonletters with periods, so it's a gmail-ish form.

"""

from __future__ import absolute_import, division, print_function, unicode_literals
from six import text_type
import re, sys

from .util import *

__all__ = ('parse_name encode_name normalize_surname sniff_url '
           'classify_pub_ref doi_to_maybe_bibcode autolearn_pub '
           'print_generic_listing parse_search').split ()


def parse_name (text):
    parts = text.rsplit (' ', 1)
    if len (parts) == 1:
        return '', parts[0].replace ('_', ' ')
    return parts[0], parts[1].replace ('_', ' ')


def encode_name (given, family):
    if not len (given):
        return family.replace (' ', '_')
    return given + ' ' + family.replace (' ', '_')


def normalize_surname (name):
    from unicodedata import normalize
    # this strips accents:
    name = normalize ('NFKD', text_type (name)).encode ('ascii', 'ignore').decode('ascii')
    # now strip non-letters and condense everything:
    return re.sub (r'\.\.+', '.', re.sub (r'[^a-z]+', '.', name.lower ()))


_arxiv_re_1 = re.compile (r'^\d\d[01]\d\.\d+')
_arxiv_re_2 = re.compile (r'^[a-z-]+/\d+')
_bibcode_re = re.compile (r'^\d\d\d\d[a-zA-Z0-9&]+')
_doi_re = re.compile (r'^10\.\d+/.*')
_fasy_re = re.compile (r'.*\.(\d+|\*)$')

def classify_pub_ref (text):
    """Given some text that we believe identifies a publication, try to
    figure out how it does so."""

    if text[0] == '%':
        return 'lastlisting', text[1:]

    if text.startswith ('http'):
        kind, value = sniff_url (text)
        if kind is not None:
            return kind, value
        # TODO: if it's really a URL, try downloading the page and identifying
        # the text from the HTML headers that most journals embed in their
        # abstract pages.

    if text.startswith ('doi:'):
        return 'doi', text[4:]

    if _doi_re.match (text) is not None:
        return 'doi', text

    if _bibcode_re.match (text) is not None:
        return 'bibcode', text

    if _arxiv_re_1.match (text) is not None:
        return 'arxiv', text

    if _arxiv_re_2.match (text) is not None:
        return 'arxiv', text

    if text.startswith ('arxiv:'):
        return 'arxiv', text[6:]

    if _fasy_re.match (text) is not None:
        # This test should go very low since it's quite open-ended.
        surname, year = text.rsplit ('.', 1)
        return 'nfasy', normalize_surname (surname) + '.' + year

    return 'nickname', text


def sniff_url (url):
    """Should return classifiers consistent with classify_pub_ref."""

    from .webutil import urlunquote

    p = 'http://dx.doi.org/'
    if url.startswith (p):
        return 'doi', urlunquote (url[len (p):])

    p = 'http://adsabs.harvard.edu/abs/'
    if url.startswith (p):
        return 'bibcode', urlunquote (url[len (p):])

    p = 'http://adsabs.harvard.edu/cgi-bin/nph-bib_query?bibcode='
    if url.startswith (p):
        return 'bibcode', urlunquote (url[len (p):])

    p = 'http://labs.adsabs.harvard.edu/ui/abs/'
    if url.startswith (p):
        return 'bibcode', urlunquote (url[len (p):])

    p = 'http://labs.adsabs.harvard.edu/adsabs/abs/'
    if url.startswith (p):
        if url[-1] == '/':
            url = url[:-1]
        return 'bibcode', urlunquote (url[len (p):])

    for p in ('http://arxiv.org/abs/', 'https://arxiv.org/abs/',
              'http://arxiv.org/pdf/', 'https://arxiv.org/pdf/'):
        if url.startswith (p):
            return 'arxiv', urlunquote (url[len (p):])

    return None, None


def doi_to_maybe_bibcode (app, doi):
    from .ads import _run_ads_search

    terms = ['doi:' + doi]

    try:
        r = _run_ads_search (app, terms, [])
    except Exception as e:
        warn ('could not perform ADS search: %s', e)
        return None

    if 'response' in r and 'docs' in r['response']:
        docs = r['response']['docs']
    else:
        warn ('malformed response from ADS for DOI-to-bibcode search (1)')
        return None

    nhits = 0
    bibcodes = set ()

    for doc in docs:
        if 'bibcode' in doc:
            bibcodes.add (doc['bibcode'])

    if not len (bibcodes):
        return None
    elif len (bibcodes) > 1:
        warn ('multiple bibcodes matched the same DOI: %s', ', '.join (bibcodes))

    return list (bibcodes)[0]


def autolearn_pub (app, text):
    kind, text = classify_pub_ref (text)

    if kind == 'lastlisting':
        # If we got here, it doesn't exist
        from . import PubLocateError
        raise PubLocateError ('no such publication "%%%s"', text)

    if kind == 'doi':
        # ADS seems to have better data quality.
        bc = doi_to_maybe_bibcode (app, text)
        if bc is not None:
            print ('[Associated', text, 'to', bc + ']')
            kind, text = 'bibcode', bc

    if kind == 'doi':
        from .crossref import autolearn_doi
        return autolearn_doi (app, text)

    if kind == 'bibcode':
        from .ads import autolearn_bibcode
        return autolearn_bibcode (app, text)

    if kind == 'arxiv':
        from .arxiv import autolearn_arxiv
        return autolearn_arxiv (app, text)

    die ('cannot auto-learn publication "%s"', text)


def print_generic_listing (db, pub_seq, sort='year', stream=None):
    info = []
    maxnfaslen = 0
    maxnicklen = 0

    if stream is None:
        # We have to do the default this way to pick up the encoder-wrapped
        # version of sys.stdout set up in App.__init__ ().
        stream = sys.stdout

    red, reset = get_color_codes (stream, 'red', 'reset')

    # TODO: number these, and save the results in a table so one can write
    # "bib read %1" to read the top item of the most recent listing.

    for pub in pub_seq:
        nfas = pub.nfas or '(no author)'
        year = pub.year or '????'
        title = pub.title or '(no title)'
        nick = db.choose_pub_nickname (pub.id) or ''

        if isinstance (year, int):
            year = '%04d' % year

        info.append ((nfas, year, title, nick, pub.id))
        maxnfaslen = max (maxnfaslen, len (nfas))
        maxnicklen = max (maxnicklen, len (nick))

    maxidxlen = len (str (len (info)))
    ofs = maxidxlen + maxnfaslen + maxnicklen + 12

    if sort is None:
        pass
    elif sort == 'year':
        info.sort (key=lambda t: t[1])
    else:
        raise ValueError ('illegal print_generic_listing sort type "%s"' % sort)

    db.execute ('DELETE FROM publists WHERE name == ?', ('last_listing', ))

    for i, (nfas, year, title, nick, id) in enumerate (info):
        print ('%s%%%-*d%s  %*s.%s  %*s  ' % (red, maxidxlen, i + 1, reset,
                                              maxnfaslen, nfas, year,
                                              maxnicklen, nick), end='', file=stream)
        print_truncated (title, ofs, stream=stream, color='bold')
        db.execute ('INSERT INTO publists VALUES (?, ?, ?)', ('last_listing',
                                                              i, id))


# Searching

def parse_search (interms):
    """We go to the trouble of parsing searches ourselves because ADS's syntax
    is quite verbose. Terms we support:

    (integer) -> year specification
       if this year is 2014, 16--99 are treated as 19NN,
       and 00--15 is treated as 20NN (for "2015 in prep" papers)
       Otherwise, treated as a full year.

    "+ref"
       Limit to refereed publications

    (any other single word)
       Treated as author surname.

    """
    outterms = []
    bareword = None

    from time import localtime
    thisyear = localtime ()[0]
    next_twodigit_year = (thisyear + 1) % 100

    for interm in interms:
        try:
            asint = int (interm)
        except ValueError:
            pass
        else:
            if asint < 100:
                if asint > next_twodigit_year:
                    outterms.append (('year', asint + (thisyear // 100 - 1) * 100))
                else:
                    outterms.append (('year', asint + (thisyear // 100) * 100))
            else:
                outterms.append (('year', asint))
            continue

        if interm == '+ref':
            outterms.append (('refereed', True))
            continue

        # It must be the bareword
        if bareword is None:
            bareword = interm
            continue

        die ('searches only support a single "bare word" right now')

    if bareword is not None:
        outterms.append (('surname', bareword)) # note the assumption here

    return outterms
