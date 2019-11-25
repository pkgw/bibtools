# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2019 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Downloading PDFs automagically.
"""

from __future__ import absolute_import, division, print_function
import io, os, re
from hashlib import sha1

from .util import *
from . import webutil as wu

__all__ = 'try_fetch_pdf'.split()

DEBUG_FETCH = (len(os.environ.get('BIBTOOLS_DEBUG_FETCH', '')) > 0)


def try_fetch_pdf(proxy, destpath, arxiv=None, bibcode=None, doi=None, max_attempts=5):
    """Given reference information, download a PDF to a specified path. Returns
    the SHA1 sum of the PDF as a hexadecimal string, or None if we couldn't
    figure out how to download it."""

    pdfurl = None

    if doi is not None:
        jurl = doi_to_journal_url(doi)
        print('[Attempting to scrape', jurl, '...]')
        try:
            pdfurl = proxy.unmangle(scrape_pdf_url(proxy.open(jurl)))
        except wu.HTTPError as e:
            warn('got HTTP error %s (%s) when trying to fetch %s', e.code,
                 e.reason, e.url)
            return None

    if pdfurl is None and bibcode is not None:
        pdfurl = bibcode_to_maybe_pdf_url(bibcode)

    if pdfurl is None and arxiv is not None:
        # Always prefer non-preprints. I need to straighten out how I'm going
        # to deal with them ...
        pdfurl = 'http://arxiv.org/pdf/' + wu.urlquote(arxiv) + '.pdf'

    if pdfurl is None:
        return None

    # OK, we can now download and register the PDF, though we might have to
    # scrape through a few layers. TODO: progress reporting, etc.

    attempts = 0
    resp = None

    while attempts < max_attempts:
        attempts += 1
        print('[Trying', pdfurl, '...]')

        try:
            resp = proxy.open(pdfurl)
        except wu.HTTPError as e:
            if e.code == 404 and wu.urlparse(pdfurl)[1] == 'articles.adsabs.harvard.edu':
                warn('ADS doesn\'t actually have the PDF on file')
                # ADS gave us a URL that turned out to be a lie. Try again,
                # ignoring it.
                return try_fetch_pdf(proxy, destpath, arxiv=arxiv, bibcode=None,
                                     doi=doi)

            warn('got HTTP error %s (%s) when trying to fetch %s', e.code, e.reason, e.url)
            return None

        # can get things like "text/html;charset=UTF-8":
        if resp.getheader('Content-Type', 'undefined').startswith('text/html'):
            # A lot of journals wrap their "PDF" links in an HTML shim. We just
            # recurse our HTML scraping.
            if DEBUG_FETCH:
                print('DEBUG: the response appears to be another HTML page')
            pdfurl = proxy.unmangle(scrape_pdf_url(resp))
            resp = None
            if pdfurl is None:
                warn('couldn\'t find PDF link; debug with BIBTOOLS_DEBUG_FETCH=y')
                return None
            continue

        # OK, we're happy with what we got.
        break

    if resp is None:
        warn('too many links when trying to find actual PDF')
        return None

    s = sha1()
    first = True

    with io.open(destpath, 'wb') as f:
        while True:
            b = resp.read(4096)

            if first:
                if len(b) < 4 or b[:4] != b'%PDF':
                    warn('response does not seem to be a PDF')
                    resp.close()
                    f.close()
                    os.unlink(destpath)
                    return None
                first = False

            if not len(b):
                break

            s.update(b)
            f.write(b)

    return s.hexdigest()


class PDFUrlScraper(wu.HTMLParser):
    """Observed places to look for PDF URLs:

    <meta> tag with name=citation_pdf_url -- IOP
    <a> tag with id=download-pdf -- Nature (non-mobile site, newer)
    <a> tag with class=download-pdf -- Nature (older)
    <a> tag with class=pdf -- AIP
    <a> tag with 'pdf-button-main' in class -- IOP through Harvard proxy
    <a> tag with id=pdfLink -- ScienceDirect
    <iframe id="pdfDocument" src="..."> -- Wiley Online Library, inner PDF wrapper
    """

    _bad_iop_cpu = re.compile(r'.*iopscience\.iop\.org.*/pdf.*pdf$')

    def __init__(self, cururl):
        wu.HTMLParser.__init__(self)
        self.cururl = cururl
        self.pdfurl = None
        self.in_script = False


    def maybe_set_pdfurl(self, url):
        # Sometimes we recurse because the "PDF" link really gives you a link
        # to a thin wrapper page, and at least in the case of Wiley the wrapper
        # then has links that point to itself. So we don't accept the potential
        # URL if it's the same thing as what we're currently reading.
        url = wu.urljoin(self.cururl, url)
        if url != self.cururl:
            self.pdfurl = url


    def handle_starttag(self, tag, attrs):
        if self.pdfurl is not None:
            return

        if tag == 'meta':
            attrs = dict(attrs)
            if attrs.get('name') == 'citation_pdf_url':
                url = attrs['content']
                # Gross hack for busted IOP links. Should probably just
                # remember multiple PDF links and cascade through if various
                # ones give errors.
                if not self._bad_iop_cpu.match(url):
                    self.maybe_set_pdfurl(url)
        elif tag == 'a':
            attrs = dict(attrs)
            if DEBUG_FETCH:
                print('DEBUG: <a> tag:', attrs)
            if attrs.get('id') == 'download-pdf':
                self.maybe_set_pdfurl(attrs['href'])
            elif attrs.get('id') == 'pdfLink':
                self.maybe_set_pdfurl(attrs['href'])
            elif attrs.get('class') == 'download-pdf':
                self.maybe_set_pdfurl(attrs['href'])
            elif attrs.get('class') == 'pdf':
                self.maybe_set_pdfurl(attrs['href'])
            elif 'pdf-button-main' in attrs.get('class', ''):
                self.maybe_set_pdfurl(attrs['href'])
            elif (attrs.get('href') or '').endswith('?acceptTC=true'):
                # JSTOR makes you click through to indicate acceptance of
                # their terms and conditions. Your use of this code indicates
                # that you accept their terms.
                self.maybe_set_pdfurl(attrs['href'])
        elif tag == 'iframe':
            attrs = dict(attrs)
            if DEBUG_FETCH:
                print('DEBUG: <iframe> tag:', attrs)
            if attrs.get('id') == 'pdfDocument':
                self.maybe_set_pdfurl(attrs['src'])
        elif tag == 'script':
            self.in_script = True


    def handle_endtag(self, tag):
        if self.pdfurl is not None:
            return

        if tag == 'script':
            self.in_script = False


    def handle_data(self, data):
        """This function is needed for Wiley's Online Library, where the PDF that you
        see in the browser window turns out to be a big iframe with document
        source URL that is only set in JavaScript. The magic line in the JS
        looks like:

        ```
        var src = "/doi/pdfdirect/10.1029/1999JA005089";
        ```

        So, here we go.

        """
        if not self.in_script:
            return

        for line in data.splitlines():
            line = line.strip()
            if not len(line):
                continue

            if DEBUG_FETCH:
                print('DEBUG: <script> data:', line)

            if line.startswith('var src = "/doi/pdfdirect/'):
                # This parsing is lame, but we're so specific that I'm not
                # worried.
                self.maybe_set_pdfurl(line.split('"')[1])
                return


def scrape_pdf_url(resp):
    return wu.parse_http_html(resp, PDFUrlScraper(resp.url)).pdfurl


def doi_to_journal_url(doi):
    return wu.get_url_from_redirection('http://dx.doi.org/' + wu.urlquote(doi))


def bibcode_to_maybe_pdf_url(bibcode):
    """Use ADS to try to get a PDF fulltext URL for the given bibcode.

    """
    url = 'https://ui.adsabs.harvard.edu/link_gateway/%s/article' % wu.urlquote(bibcode)
    return wu.get_url_from_redirection(url, notfound_ok=True)
