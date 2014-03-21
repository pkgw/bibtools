# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Downloading PDFs automagically.
"""

__all__ = ('try_fetch_pdf').split ()

from hashlib import sha1

from .util import *
from . import webutil as wu


def try_fetch_pdf (proxy, destpath, arxiv=None, bibcode=None, doi=None):
    """Given reference information, download a PDF to a specified path. Returns
    the SHA1 sum of the PDF as a hexadecimal string, or None if we couldn't
    figure out how to download it."""

    pdfurl = None

    if doi is not None:
        jurl = doi_to_journal_url (doi)
        print '[Attempting to scrape', jurl, '...]'
        pdfurl = proxy.unmangle (scrape_pdf_url (proxy.open (jurl)))

    if pdfurl is None and bibcode is not None:
        # This never returns None: ADS will always give a URL, but it may just
        # be that the URL resolves to a 404 page saying that ADS has no PDF
        # available. Thus, this technique is always our last resort.
        pdfurl = bibcode_to_maybe_pdf_url (bibcode)

    if pdfurl is None and arxiv is not None:
        # Always prefer non-preprints. I need to straighten out how I'm going
        # to deal with them ...
        pdfurl = 'http://arxiv.org/pdf/' + wu.urlquote (arxiv) + '.pdf'

    if pdfurl is None:
        return None

    # OK, we can now download and register the PDF. TODO: progress reporting,
    # etc.

    s = sha1 ()

    print '[Trying', pdfurl, '...]'

    try:
        resp = proxy.open (pdfurl)
    except wu.HTTPError as e:
        if e.code == 404 and wu.urlparse (pdfurl)[1] == 'articles.adsabs.harvard.edu':
            warn ('ADS doesn\'t actually have the PDF on file')
            return None # ADS gave us a URL that turned out to be a lie.
        raise

    first = True

    with open (destpath, 'w') as f:
        while True:
            b = resp.read (4096)

            if first:
                if len (b) < 4 or b[:4] != '%PDF':
                    warn ('response does not seem to be a PDF')
                    resp.close ()
                    f.close ()
                    os.unlink (temppath)
                    return None
                first = False

            if not len (b):
                break

            s.update (b)
            f.write (b)

    return s.hexdigest ()


class PDFUrlScraper (wu.HTMLParser):
    """Observed places to look for PDF URLs:

    <meta> tag with name=citation_pdf_url -- IOP
    <a> tag with id=download-pdf -- Nature (non-mobile site, newer)
    <a> tag with class=download-pdf -- Nature (older)
    <a> tag with class=pdf -- AIP
    """

    def __init__ (self):
        wu.HTMLParser.__init__ (self)
        self.pdfurl = None


    def handle_starttag (self, tag, attrs):
        if self.pdfurl is not None:
            return

        if tag == 'meta':
            attrs = dict (attrs)
            if attrs.get ('name') == 'citation_pdf_url':
                self.pdfurl = attrs['content']
        elif tag == 'a':
            attrs = dict (attrs)
            if attrs.get ('id') == 'download-pdf':
                self.pdfurl = attrs['href']
            elif attrs.get ('class') == 'download-pdf':
                self.pdfurl = attrs['href']
            elif attrs.get ('class') == 'pdf':
                self.pdfurl = attrs['href']


def scrape_pdf_url (resp):
    parser = wu.parse_http_html (resp, PDFUrlScraper ())
    if parser.pdfurl is None:
        return None

    return wu.urljoin (resp.url, parser.pdfurl)


def doi_to_journal_url (doi):
    return wu.get_url_from_redirection ('http://dx.doi.org/' + wu.urlquote (doi))


def bibcode_to_maybe_pdf_url (bibcode):
    """If ADS doesn't have a fulltext link for a given bibcode, it will return a link
    to articles.ads.harvard.edu that in turn yields an HTML error page.

    Also, the Location header returned by the ADS server appears to be slightly broken,
    with the &'s in the URL being HTML entity-encoded to &amp;s."""

    url = ('http://adsabs.harvard.edu/cgi-bin/nph-data_query?link_type=ARTICLE&bibcode='
           + wu.urlquote (bibcode))
    pdfurl = wu.get_url_from_redirection (url)
    return pdfurl.replace ('&amp;', '&')
