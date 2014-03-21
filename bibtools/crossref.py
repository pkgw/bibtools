# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Things related to the CrossRef/DOI/OpenURL system.
"""

__all__ = ('autolearn_doi').split ()

import xml.etree.ElementTree as ET

from . import webutil as wu


def _translate_unixref_name (personelem):
    # XXX: deal with "The Fermi-LAT Collaboration", "Gopal-Krishna", etc. I
    # don't know what the standard specifies.

    given = personelem.find ('given_name').text
    sur = personelem.find ('surname').text
    return given + ' ' + sur.replace (' ', '_')


def autolearn_doi (doi):
    # TODO: editors. See e.g. unixref output for 10.1007/978-3-642-14335-9_1
    # -- three <contributors> sections (!), with contributor_role="editor" on
    # the <person_name> element.

    # XXX loading config scattershot as-needed isn't ideal ...
    from .config import BibConfig
    apikey = BibConfig ().get_or_die ('api-keys', 'crossref')

    url = ('http://crossref.org/openurl/?id=%s&noredirect=true&pid=%s&'
           'format=unixref' % (urlquote (doi), wu.urlquote (apikey)))
    info = {'doi': doi, 'keep': 0} # because we're autolearning

    # XXX sad to be not doing this incrementally, but Py 2.x doesn't
    # seem to have an incremental parser built in.

    print '[Parsing', url, '...]'
    xmldoc = ''.join (wu.urllib2.urlopen (url))
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
