# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
The main database.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import collections, json, sqlite3, sys

from . import PubLocateError, MultiplePubsError
from .util import *
from .bibcore import *

__all__ = ('connect init').split ()


dbpath = bibpath ('db.sqlite3')

def connect ():
    return sqlite3.connect (dbpath, factory=BibDB)


def init (app):
    import os.path

    init = datastream ('schema.sql').read ()

    mkdir_p (bibpath ())

    if os.path.exists (dbpath):
        die ('the file "%s" already exists', dbpath)

    try:
        app.db.executescript (init)
    except sqlite3.OperationalError as e:
        die ('cannot initialize "%s": %s', dbpath, e)


PubRow = collections.namedtuple ('PubRow',
                                 'id abstract arxiv bibcode doi keep nfas '
                                 'refdata title year'.split ())

AuthorNameRow = collections.namedtuple ('AuthorNameRow',
                                        ['name'])

AuthorRow = collections.namedtuple ('AuthorRow',
                                    'type pubid idx authid'.split ())

HistoryRow = collections.namedtuple ('HistoryRow',
                                     'date pubid action'.split ())

NicknameRow = collections.namedtuple ('NicknameRow',
                                      'nickname pubid'.split ())

PdfRow = collections.namedtuple ('PdfRow',
                                 'sha1 pubid'.split ())

authtypes = {'author': 0, 'editor': 1}
histactions = {'read': 1, 'visit': 2}


def nt_augment (ntclass, **vals):
    for k in vals.keys ():
        if k not in ntclass._fields:
            raise ValueError ('illegal field "%s" for creating %s instance'
                              % (k, ntclass.__name__))
    return ntclass (*tuple (vals.get (k) for k in ntclass._fields))


class BibDB (sqlite3.Connection):
    def getfirst (self, fmt, *args):
        """Returns the tuple from sqlite3, or None."""
        return self.execute (fmt, args).fetchone ()


    def getfirstval (self, fmt, *args):
        """Assumes that the query returns a single column. Returns the first value, or
        None."""
        v = self.getfirst (fmt, *args)
        if v is None:
            return None
        return v[0]


    def pub_fquery (self, q, *args):
        c = self.cursor ()
        c.row_factory = lambda curs, tup: PubRow (*tup)
        return c.execute (q, args)


    def pub_query (self, partial, *args):
        return self.pub_fquery ('SELECT * FROM pubs WHERE ' + partial, *args)


    def learn_pub_authors (self, pubid, authtype, authors):
        authtype = authtypes[authtype]
        c = self.cursor ()

        for idx, auth in enumerate (authors):
            # Based on reading StackExchange, there's no cleaner way to do this,
            # but the SELECT should be snappy.
            c.execute ('INSERT OR IGNORE INTO author_names VALUES (?)',
                       (auth, ))
            row = self.getfirst ('SELECT oid FROM author_names WHERE name = ?', auth)[0]
            c.execute ('INSERT OR REPLACE INTO authors VALUES (?, ?, ?, ?)',
                       (authtype, pubid, idx, row))


    def get_pub_authors (self, pubid, authtype='author'):
        authtype = authtypes[authtype]

        return (parse_name (a[0]) for a in
                self.execute ('SELECT name FROM authors AS au, author_names AS an '
                              'WHERE au.type == ? AND au.authid == an.oid '
                              '  AND au.pubid == ? '
                              'ORDER BY idx', (authtype, pubid, )))


    def get_pub_fas (self, pubid):
        """FAS = first-author surname. May return None. We specifically are retrieving
        the un-normalized version here, so we don't use the value stored in
        the 'pubs' table."""

        for t in self.execute ('SELECT name FROM authors AS au, author_names AS an '
                               'WHERE au.type == ? AND au.authid == an.oid '
                               '  AND au.pubid == ? '
                               'AND idx == 0', (authtypes['author'], pubid, )):
            return parse_name (t[0])[1]

        return None


    def choose_pub_nickname (self, pubid):
        # barring any particularly meaningful information, go with the
        # shortest nickname. Returns None if none present.

        n = list (self.execute ('SELECT nickname FROM nicknames '
                                'WHERE pubid == ? '
                                'ORDER BY length(nickname) ASC LIMIT 1', (pubid, )))

        if not len (n):
            return None
        return n[0][0]


    def _lint_refdata (self, info):
        rd = info['refdata']

        if rd.get ('journal') == 'ArXiv e-prints':
            warn ('useless "ArXiv e-prints" bibliographical record')


    def _fill_pub (self, info, pubid):
        """Note that `info` will be mutated.

        If pubid is None, a new record will be created; otherwise it will
        be updated."""

        authors = info.pop ('authors', ())
        editors = info.pop ('editors', ())
        nicknames = info.pop ('nicknames', ())

        if 'abstract' in info:
            info['abstract'] = squish_spaces (info['abstract'])
        if 'title' in info:
            info['title'] = squish_spaces (info['title'])

        if authors:
            info['nfas'] = normalize_surname (parse_name (authors[0])[1])

        if 'refdata' in info:
            self._lint_refdata (info)
            info['refdata'] = json.dumps (info['refdata'])

        row = nt_augment (PubRow, **info)
        c = self.cursor ()

        if pubid is not None:
            # not elegant but as far as I can tell there's no alternative.
            c.execute ('UPDATE pubs SET abstract=?, arxiv=?, bibcode=?, '
                       '  doi=?, keep=?, nfas=?, refdata=?, title=?, year=? '
                       'WHERE id == ?', row[1:] + (pubid, ))
        else:
            c.execute ('INSERT INTO pubs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', row)
            pubid = c.lastrowid

        if authors:
            self.learn_pub_authors (pubid, 'author', authors)

        if editors:
            self.learn_pub_authors (pubid, 'editor', editors)

        if nicknames:
            for nickname in nicknames:
                try:
                    c.execute ('INSERT INTO nicknames VALUES (?, ?)',
                               (nickname, pubid))
                except sqlite3.IntegrityError:
                    die ('duplicated pub nickname "%s"', nickname)

        tmp = list (row)
        tmp[0] = pubid
        return PubRow (*tmp)


    def learn_pub (self, info):
        """Note that `info` will be mutated."""
        return self._fill_pub (info, None)


    def update_pub (self, pub, info):
        info['keep'] = pub.keep

        self.execute ('DELETE FROM authors WHERE pubid == ?', (pub.id, ))
        self.execute ('DELETE FROM nicknames WHERE pubid == ?', (pub.id, ))
        # XXX later maybe:
        #self.execute ('DELETE FROM notes WHERE pubid == ?', (pub.id, ))
        #self.execute ('DELETE FROM publists WHERE pubid == ?', (pub.id, ))

        return self._fill_pub (info, pub.id)


    def delete_pub (self, pubid):
        sha1 = self.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid == ?', pubid)
        if sha1 is not None:
            warn ('orphaning file %s', libpath (sha1, 'pdf'))

        self.execute ('DELETE FROM authors WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM history WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM nicknames WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM notes WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM pdfs WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM publists WHERE pubid == ?', (pubid, ))
        self.execute ('DELETE FROM pubs WHERE id == ?', (pubid, ))

        # at some point the author_names table will need rebuilding, but
        # I don't think we should worry about that here.


    def jsonify_pub (self, pubid):
        """The data structure here should be, to the best of our effort, compatible
        with the one accepted by learn_pub().

        """
        pub = self.pub_query ('id == ?', pubid).fetchone ()

        info = {}
        info['authors'] = [encode_name (*n) for n in self.get_pub_authors (pubid, 'author')]
        info['editors'] = [encode_name (*n) for n in self.get_pub_authors (pubid, 'editor')]
        info['abstract'] = pub.abstract
        info['title'] = pub.title
        info['arxiv'] = pub.arxiv
        info['bibcode'] = pub.bibcode
        info['doi'] = pub.doi
        info['year'] = pub.year
        info['nicknames'] = list (self.execute ('SELECT nickname FROM nicknames '
                                                'WHERE pubid == ?', (pubid, )))
        info['refdata'] = json.loads (pub.refdata)

        return info


    def log_action (self, pubid, actionid):
        import time
        actionid = histactions[actionid]
        self.execute ('INSERT INTO history VALUES (?, ?, ?)',
                      (int (time.time ()), pubid, actionid))
