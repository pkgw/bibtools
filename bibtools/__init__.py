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


def _translate_ads_name (name):
    pieces = [x.strip () for x in name.split (',', 1)]
    surname = pieces[0].replace (' ', '_')

    if len (pieces) > 1:
        return pieces[1] + ' ' + surname
    return surname


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


def _autolearn_bibcode_tag (info, tag, text):
    # TODO: editors?

    if tag == 'T':
        info['title'] = text
    elif tag == 'D':
        info['year'] = int (text.split ('/')[-1])
    elif tag == 'B':
        info['abstract'] = text
    elif tag == 'A':
        info['authors'] = [_translate_ads_name (n) for n in text.split (';')]
    elif tag == 'Y':
        subdata = dict (s.strip ().split (': ', 1)
                        for s in text.split (';'))

        if 'DOI' in subdata:
            info['doi'] = subdata['DOI']
        if 'eprintid' in subdata:
            value = subdata['eprintid']
            if value.startswith ('arXiv:'):
                info['arxiv'] = value[6:]


def autolearn_bibcode (bibcode):
    # XXX could/should convert this to an ADS 2.0 record search, something
    # like http://adslabs.org/adsabs/api/record/{doi}/?dev_key=...

    url = ('http://adsabs.harvard.edu/cgi-bin/nph-abs_connect?'
           'data_type=PORTABLE&nocookieset=1&bibcode=' + urlquote (bibcode))

    info = {'bibcode': bibcode, 'keep': 0} # because we're autolearning
    curtag = curtext = None

    print '[Parsing', url, '...]'

    for line in urllib2.urlopen (url):
        line = line.decode ('iso-8859-1').strip ()

        if not len (line):
            if curtag is not None:
                _autolearn_bibcode_tag (info, curtag, curtext)
                curtag = curtext = None
            continue

        if curtag is None:
            if line[0] == '%':
                # starting a new tag
                curtag = line[1]
                curtext = line[3:]
            elif line.startswith ('Retrieved '):
                if not line.endswith ('selected: 1.'):
                    die ('matched more than one publication')
        else:
            if line[0] == '%':
                # starting a new tag, while we had one going before.
                # finish up the previous
                _autolearn_bibcode_tag (info, curtag, curtext)
                curtag = line[1]
                curtext = line[3:]
            else:
                curtext += ' ' + line

    if curtag is not None:
        _autolearn_bibcode_tag (info, curtag, curtext)

    return info


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


# Searching ADS

def _run_ads_search (searchterms, filterterms):
    # TODO: access to more API args
    import urllib, json

    apikey = BibConfig ().get_or_die ('api-keys', 'ads')

    q = [('q', ' '.join (searchterms)),
         ('dev_key', apikey)]

    for ft in filterterms:
        q.append (('filter', ft))

    url = 'http://adslabs.org/adsabs/api/search?' + urllib.urlencode (q)
    return json.load (urllib2.urlopen (url))


def parse_search (interms):
    """We go to the trouble of parsing searches ourselves because ADS's syntax
    is quite verbose. Terms we support:

    (integer) -> year specification
       if this year is 2014, 16--99 are treated as 19NN,
       and 00--15 is treated as 20NN (for "2015 in prep" papers)
       Otherwise, treated as a full year.
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

        # It must be the bareword
        if bareword is None:
            bareword = interm
            continue

        die ('searches only support a single "bare word" right now')

    if bareword is not None:
        outterms.append (('surname', bareword)) # note the assumption here

    return outterms


def search_ads (terms, raw=False):
    if len (terms) < 2:
        die ('require at least two search terms for ADS')

    adsterms = []

    for info in terms:
        if info[0] == 'year':
            adsterms.append ('year:%d' % info[1])
        elif info[0] == 'surname':
            adsterms.append ('author:"%s"' % info[1])
        else:
            die ('don\'t know how to express search term %r to ADS', info)

    r = _run_ads_search (adsterms, ['database:astronomy']) # XXX more hardcoding

    if raw:
        out = codecs.getwriter ('utf-8') (sys.stdout)
        json.dump (r, out, ensure_ascii=False, indent=2, separators=(',', ': '))
        return

    maxnfaslen = 0
    maxbclen = 0
    info = []

    for item in r['results']['docs'][:20]:
        # year isn't important since it's embedded in bibcode.
        title = item['title'][0] # not sure why this is a list?
        bibcode = item['bibcode']
        nfas = normalize_surname (parse_name (_translate_ads_name (item['author'][0]))[1])

        maxnfaslen = max (maxnfaslen, len (nfas))
        maxbclen = max (maxbclen, len (bibcode))
        info.append ((bibcode, nfas, title))

    ofs = maxnfaslen + maxbclen + 4

    for bc, nfas, title in info:
        print '%*s  %*s  ' % (maxbclen, bc, maxnfaslen, nfas),
        print_truncated (title, ofs)


# Text export/import

def text_export_one (db, pub, write, width):
    # Title and year
    if pub.title is None:
        write ('--no title--\n')
    else:
        print_linewrapped (pub.title, width=width, write=write)
    if pub.year is None:
        write ('--no year--\n')
    else:
        write (str (pub.year))
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
    for (nick, ) in db.execute ('SELECT nickname FROM nicknames WHERE pubid == ? '
                                'ORDER BY nickname asc', (pub.id, )):
        write ('nick = ')
        write (nick)
        write ('\n')
    write ('\n')

    # Authors
    anyauth = False
    for given, family in db.get_pub_authors (pub.id):
        write (encode_name (given, family))
        write ('\n')
        anyauth = True
    if not anyauth:
        write ('--no authors--\n')
    firsteditor = True
    for given, family in db.get_pub_authors (pub.id, AUTHTYPE_EDITOR):
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

        for k in sorted (rd.iterkeys ()):
            write (k)
            write (' = ')
            write (rd[k])
            write ('\n')
    write ('\n')

    # Abstract
    if pub.abstract is None:
        write ('--no abstract--\n')
    else:
        print_linewrapped (pub.abstract, width=width, write=write, maxwidth=72)
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


def text_import_one (stream):
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
