# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Global structure for the bibliography tool.
"""

__all__ = ('BibApp BibError PubLocateError MultiplePubsError').split ()


class BibError (Exception):
    def __init__ (self, fmt, *args):
        if not len (args):
            self.bibmsg = str (fmt)
        else:
            self.bibmsg = fmt % args

    def __str__ (self):
        return self.bibmsg


class PubLocateError (BibError):
    pass

class MultiplePubsError (PubLocateError):
    pass


class BibApp (object):
    _thedb = None
    _thecfg = None
    _theproxy = None

    @property
    def db (self):
        if self._thedb is None:
            from .db import connect
            self._thedb = connect ()
        return self._thedb


    @property
    def cfg (self):
        if self._thecfg is None:
            from .config import BibConfig
            self._thecfg = BibConfig ()
        return self._thecfg


    @property
    def proxy (self):
        if self._theproxy is None:
            from .proxy import get_proxy
            self._theproxy = get_proxy (self.cfg)
        return self._theproxy


    def __enter__ (self):
        return self


    def __exit__ (self, etype, evalue, etb):
        if self._thedb is not None:
            self._thedb.commit ()
            self._thedb.close ()


    # Global-level helpers

    def locate_pubs (self, textids, noneok=False, autolearn=False):
        from .bibcore import classify_pub_ref

        for textid in textids:
            kind, text = classify_pub_ref (textid)
            q = matchtext = None

            if kind == 'doi':
                q = self.db.pub_query ('doi = ?', text)
                matchtext = 'DOI = ' + text
            elif kind == 'bibcode':
                q = self.db.pub_query ('bibcode = ?', text)
                matchtext = 'bibcode = ' + text
            elif kind == 'arxiv':
                q = self.db.pub_query ('arxiv = ?', text)
                matchtext = 'arxiv = ' + text
            elif kind == 'nickname':
                q = self.db.pub_fquery ('SELECT p.* FROM pubs AS p, nicknames AS n '
                                  'WHERE p.id == n.pubid AND n.nickname = ?', text)
                matchtext = 'nickname = ' + text
            elif kind == 'nfasy':
                nfas, year = text.rsplit ('.', 1)
                if year == '*':
                    q = self.db.pub_query ('nfas = ?', nfas)
                else:
                    q = self.db.pub_query ('nfas = ? AND year = ?', nfas, year)
                matchtext = 'surname/year ~ ' + text
            else:
                # This is a bug since we should handle every possible 'kind'
                # returned by classify_pub_ref.
                assert False

            gotany = False

            for pub in q:
                gotany = True
                yield pub

            if not gotany and autolearn:
                from .bibcore import autolearn_pub
                yield self.db.learn_pub (autolearn_pub (self, textid))
                continue

            if not gotany and not noneok:
                raise PubLocateError ('no publications matched ' + textid)


    def locate_pub (self, text, noneok=False, autolearn=False):
        if autolearn:
            noneok = True

        thepub = None

        for pub in self.locate_pubs ((text,), noneok, autolearn):
            if thepub is None:
                # First match.
                thepub = pub
            else:
                # Second match. There will be no third match.
                raise MultiplePubsError ('more than one publication matched ' + text)

        if thepub is not None:
            return thepub

        if autolearn:
            from .bibcore import autolearn_pub
            return self.db.learn_pub (autolearn_pub (self, text))

        # If we made it here, noneok must be true.
        return None


    def locate_or_die (self, text, autolearn=False):
        try:
            return self.locate_pub (text, autolearn=autolearn)
        except MultiplePubsError as e:
            print >>sys.stderr, 'error:', e
            print >>sys.stderr
            print_generic_listing (self.db, self.locate_pubs ((text,), noneok=True))
            raise SystemExit (1)
        except PubLocateError as e:
            die (e)


    def open_url (self, url):
        from .util import open_url
        open_url (self, url)


    def try_get_pdf (self, pub):
        import os
        from util import bibpath, mkdir_p, ensure_libpath_exists, libpath
        from fetchpdf import try_fetch_pdf

        mkdir_p (bibpath ('lib'))
        temppath = bibpath ('lib', 'incoming.pdf')

        sha1 = try_fetch_pdf (self.proxy, temppath, arxiv=pub.arxiv,
                              bibcode=pub.bibcode, doi=pub.doi)
        if sha1 is None:
            return None

        ensure_libpath_exists (sha1)
        destpath = libpath (sha1, 'pdf')
        os.rename (temppath, destpath)
        self.db.execute ('INSERT OR REPLACE INTO pdfs VALUES (?, ?)', (sha1, pub.id))
        return sha1
