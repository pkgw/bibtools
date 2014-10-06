# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Things related to the CrossRef/DOI/OpenURL system.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import xml.etree.ElementTree as ET

from .util import die
from . import webutil as wu

__all__ = ('autolearn_doi stream_doi').split ()


def _translate_unixref_name (personelem):
    # XXX: deal with "The Fermi-LAT Collaboration", "Gopal-Krishna", etc. I
    # don't know what the standard specifies.

    given = personelem.find ('given_name').text
    sur = personelem.find ('surname').text
    return given + ' ' + sur.replace (' ', '_')


def stream_doi (app, doi):
    """Returns tuple of URL string and a urlopen() return value."""

    apikey = app.cfg.get_or_die ('api-keys', 'crossref')
    url = ('http://crossref.org/openurl/?id=%s&noredirect=true&pid=%s&'
           'format=unixref' % (wu.urlquote (doi), wu.urlquote (apikey)))
    return url, wu.urlopen (url)


def autolearn_doi (app, doi):
    # TODO: editors. See e.g. unixref output for 10.1007/978-3-642-14335-9_1
    # -- three <contributors> sections (!), with contributor_role="editor" on
    # the <person_name> element.
    #
    # XXX sad to not parse the XML incrementally, but Py 2.x doesn't seem to
    # have an incremental parser built in (!)

    url, handle = stream_doi (app, doi)
    print ('[Parsing', url, '...]')
    root = ET.fromstring (b''.join (handle))

    infotop = root.find ('doi_record/crossref/journal')
    if infotop is not None:
        # Journal article
        authpath = 'journal_article/contributors/person_name'
        titlepath = 'journal_article/titles/title'
        yearpath = 'journal_issue/publication_date/year'

    if infotop is None:
        infotop = root.find ('doi_record/crossref/conference/conference_paper')
        if infotop is not None:
            # Conference paper
            authpath = 'contributors/person_name'
            titlepath = 'titles/title'
            yearpath = 'publication_date/year'

    if infotop is None:
        die ('don\'t know how to interpret UnixRef XML for %s', doi)

    # OK, now we can fill in the info.

    info = {'doi': doi, 'keep': 0} # because we're autolearning

    try:
        info['authors'] = [_translate_unixref_name (p) for p in
                           infotop.findall (authpath)]
    except:
        pass

    try:
        info['title'] = ' '.join (t.strip () for t in
                                  infotop.find (titlepath).itertext ())
    except:
        pass

    try:
        info['year'] = int (infotop.find (yearpath).text)
    except:
        pass

    return info
