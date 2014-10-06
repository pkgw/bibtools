# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
The command-line interface.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
import codecs, io, json, os.path, sys

from . import BibError, webutil as wu
from .util import *
from .bibcore import print_generic_listing, parse_search

__all__ = ['driver']


class UsageError (BibError):
    pass


def pop_option (ident, argv=None):
    """A lame routine for grabbing command-line arguments. Returns a boolean
    indicating whether the option was present. If it was, it's removed from
    the argument string. Because of the lame behavior, options can't be
    combined, and non-boolean options aren't supported. Operates on sys.argv
    by default.

    Note that this will proceed merrily if argv[0] matches your option.

    """
    if argv is None:
        from sys import argv

    if len (ident) == 1:
        ident = '-' + ident
    else:
        ident = '--' + ident

    found = ident in argv
    if found:
        argv.remove (ident)

    return found


def cmd_ads (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    pub = app.locate_or_die (idtext)
    if pub.bibcode is None:
        die ('cannot open ADS for this publication: no bibcode on record')

    app.db.log_action (pub.id, 'visit')
    app.open_url ('http://labs.adsabs.harvard.edu/adsabs/abs/' + wu.urlquote (pub.bibcode))


def cmd_apage (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    pub = app.locate_or_die (idtext)
    if pub.arxiv is None:
        die ('cannot open arxiv website: no identifier for record')

    app.db.log_action (pub.id, 'visit')
    app.open_url ('http://arxiv.org/abs/' + wu.urlquote (pub.arxiv))


def cmd_btexport (app, argv):
    from .bibtex import bibtex_styles, export_to_bibtex

    if len (argv) != 3:
        raise UsageError ('expected exactly 2 arguments')

    outstyle = argv[1]
    auxfile = argv[2]

    # Load/check style
    factory = bibtex_styles.get (outstyle)
    if factory is None:
        die ('unrecognized BibTeX output style "%s"', outstyle)

    style = factory ()

    # Load cited nicknames
    citednicks = set ()

    for line in io.open (auxfile, 'rt'):
        if not line.startswith (r'\citation{'):
            continue

        line = line.rstrip ()

        if line[-1] != '}':
            warn ('unexpected cite line in LaTeX aux file: "%s"', line)
            continue

        entries = line[10:-1]

        # We provide a mechanism for ignoring raw bibtex entries
        citednicks.update ([e for e in entries.split (',')
                            if not e.startswith ('r.')])

    # Ready to write
    export_to_bibtex (app, style, citednicks)


def cmd_canon_journal (app, argv):
    if len (argv) not in (3, 4):
        raise UsageError ('expected 2 or 3 arguments')

    oldjournal = argv[1]
    newjournal = argv[2]
    newissn = argv[3] if len (argv) > 3 else None

    for pub in app.db.pub_query ('refdata NOT NULL'):
        rd = json.loads (pub.refdata)
        if rd.get ('journal', '') != oldjournal:
            continue

        rd['journal'] = newjournal

        if 'issn' not in rd and newissn is not None:
            rd['issn'] = newissn

        app.db.execute ('UPDATE pubs SET refdata = ? WHERE id == ?',
                        (json.dumps (rd), pub.id))


def cmd__complete (app, argv):
    if len (argv) < 2:
        raise UsageError ('expected at least 1 argument')

    subcommand = argv[1]

    from . import completions
    completions.process (app, subcommand, argv[2:])


def cmd_delete (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    # TODO: mode to match multiple publications and delete them
    # all, if a --force flag is given.

    pub = app.locate_or_die (idtext, autolearn=True)
    app.db.delete_pub (pub.id)


def cmd_dump (app, argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    app.export_all (sys.stdout, 72)


def cmd_dump_crossref (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    # Here we have a slight wrinkle from the usual approach. If the argument
    # is a DOI, just fetch it without trying to autolearn a database entry.

    idtext = argv[1]

    from .bibcore import classify_pub_ref
    kind, content = classify_pub_ref (idtext)

    if kind == 'doi':
        doi = content
    else:
        pub = app.locate_or_die (idtext, autolearn=True)
        if pub.doi is None:
            die ('publication "%s" has no associated DOI, which is necessary', idtext)
        doi = pub.doi

    from .crossref import stream_doi
    url, handle = stream_doi (app, doi)

    for data in handle:
        sys.stdout.write (data)


def cmd_edit (app, argv):
    from . import textfmt

    from tempfile import NamedTemporaryFile

    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    pub = app.locate_or_die (idtext, autolearn=True)

    # While NamedTemporaryFile returns an existing stream, I think we're going
    # to have to manually wrap it in a codec.
    work = NamedTemporaryFile (prefix='bib.edit.', mode='wb', dir='.', delete=False)
    enc = codecs.getwriter ('utf-8') (work)
    textfmt.export_one (app, pub, enc, 72)
    work.close ()

    run_editor (work.name)

    enc = codecs.getreader ('utf-8') (open (work.name, 'rb'))
    info = textfmt.import_one (enc)
    app.db.update_pub (pub, info)

    try:
        os.unlink (work.name)
    except Exception as e:
        warn ('couldn\'t delete temporary file "%s": %s', work.name, e)

    try:
        os.unlink (work.name + '~')
    except:
        pass # whatever.


def cmd_forgetpdf (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]
    pub = app.locate_or_die (idtext)

    # It's not something I plan to do, but the schema does let us
    # store multiple PDFs for one pub ...

    any = False

    for (sha1, ) in app.db.execute ('SELECT sha1 FROM pdfs '
                                    'WHERE pubid == ?', (pub.id, )):
        print ('orphaning', libpath (sha1, 'pdf'))
        any = True

    if not any:
        warn ('no PDFs were on file for "%s"', idtext)

    app.db.execute ('DELETE FROM pdfs WHERE pubid == ?', (pub.id, ))


def cmd_grep (app, argv):
    import re

    nocase = pop_option ('i', argv)
    fixed = pop_option ('f', argv)
    refinfo = pop_option ('r', argv)

    if len (argv) != 2:
        raise UsageError ('expected exactly 1 non-option argument')

    regex = argv[1]

    if refinfo:
        fields = ['arxiv', 'bibcode', 'doi', 'refdata']
    else:
        fields = ['title', 'abstract']

    try:
        # Could use the Sqlite REGEXP machinery, but it should be somewhat
        # faster to precompile the regex. Premature optimization FTW.

        if fixed:
            def rmatch (i):
                if i is None:
                    return False
                return regex in i
        else:
            flags = 0

            if nocase:
                flags |= re.IGNORECASE

            comp = re.compile (regex, flags)

            def rmatch (i):
                if i is None:
                    return False
                return comp.search (i) is not None

        app.db.create_function ('rmatch', 1, rmatch)
        q = app.db.pub_fquery ('SELECT * FROM pubs WHERE ' +
                               '||'.join ('rmatch(%s)' % f for f in fields))
        print_generic_listing (app.db, q)
    except Exception as e:
        die (e)


def _group_cmd_add (app, argv):
    if len (argv) < 3:
        raise UsageError ('expected at least 2 arguments')

    groupname = argv[1]
    # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
    dbgroupname = 'user_' + groupname

    try:
        for pub in app.locate_pubs (argv[2:], autolearn=True):
            app.db.execute ('INSERT OR IGNORE INTO publists VALUES (?, '
                            '  (SELECT ifnull(max(idx)+1,0) FROM publists WHERE name == ?), '
                            '?)', (dbgroupname, dbgroupname, pub.id))
    except Exception as e:
        die (e)


def _group_cmd_list (app, argv):
    if len (argv) not in (1, 2):
        raise UsageError ('expected 0 or 1 arguments')

    try:
        if len (argv) == 1:
            # List the groups.
            q = app.db.execute ('SELECT DISTINCT name FROM publists WHERE '
                                'name LIKE ? ORDER BY name ASC', ('user_%', ))
            for (name, ) in q:
                print (name[5:])
        else:
            # List the items in a group.
            groupname = argv[1]
            # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
            dbgroupname = 'user_' + groupname

            q = app.db.pub_fquery ('SELECT p.* FROM pubs AS p, publists AS pl '
                                   'WHERE p.id == pl.pubid AND pl.name == ? '
                                   'ORDER BY pl.idx', dbgroupname)
            print_generic_listing (app.db, q)
    except Exception as e:
        die (e)


def _group_cmd_rm (app, argv):
    if len (argv) < 3:
        raise UsageError ('expected at least 2 arguments')

    groupname = argv[1]
    # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
    dbgroupname = 'user_' + groupname

    # We want to complain if an individual term doesn't match anything in the
    # group, but if the user specifies "williams.*" and we get a bunch of hits
    # only one of which is in the group, that's OK. So we need to process terms
    # individually.

    c = app.db.cursor ()

    try:
        for idtext in argv[2:]:
            ndeleted = 0

            for pub in app.locate_pubs ((idtext,)):
                c.execute ('DELETE FROM publists WHERE name == ? AND pubid == ?',
                           (dbgroupname, pub.id))
                ndeleted += c.rowcount

            if not ndeleted:
                warn ('no entries in "%s" matched "%s"', groupname, idtext)
    except Exception as e:
        die (e)


def cmd_group (app, argv):
    if len (argv) < 2:
        raise UsageError ('"group" requires a subcommand')

    subcmd = argv[1]
    subfunc = globals ().get ('_group_cmd_' + subcmd.replace ('-', '_'))

    if not callable (subfunc):
        die ('"%s" is not a recognized subcommand of "group"; run me without '
             'arguments for usage help', subcmd)

    subfunc (app, argv[1:])


def cmd_init (app, argv):
    from .db import init

    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    init (app)


def cmd_info (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    # TODO: should be OK to match multiple publications and print them all
    # out.

    pub = app.locate_or_die (idtext, autolearn=True)

    year = pub.year or 'no year'
    title = pub.title or '(no title)'

    authors = list (app.db.get_pub_authors (pub.id))
    if len (authors) > 10:
        authstr = ', '.join (a[1] for a in authors[:10]) + ' ...'
    elif len (authors):
        authstr = ', '.join (a[1] for a in authors)
    else:
        authstr = '(no authors)'

    bold, bred, red, reset = get_color_codes (None, 'bold', 'bold-red', 'red', 'reset')
    print_linewrapped (bred + title + reset, rest_prefix='   ')
    print_linewrapped (bold + '%s (%s)' % (authstr, year) + reset, rest_prefix='   ')

    nicks = [t[0] for t in app.db.execute ('SELECT nickname FROM nicknames '
                                           'WHERE pubid == ? '
                                           'ORDER BY nickname', (pub.id, ))]
    if len (nicks):
        print (red + 'nicknames:' + reset, *nicks)

    if pub.arxiv is not None:
        print (red + 'arxiv:' + reset, pub.arxiv)
    if pub.bibcode is not None:
        print (red + 'bibcode:' + reset, pub.bibcode)
    if pub.doi is not None:
        print (red + 'DOI:' + reset, pub.doi)
    if pub.refdata is not None:
        rd = json.loads (pub.refdata)
        txt = red + '~BibTeX:' + reset + ' @%s {' % rd.pop ('_type')
        def fmt (t):
            k, v = t
            if ' ' in v:
                return k + '="' + v + '"'
            return k + '=' + v
        bits = (fmt (t) for t in sorted (rd.iteritems (), key=lambda t: t[0]))
        txt += ', '.join (bits) + '}'
        print_linewrapped (txt, rest_prefix='   ')

    if pub.abstract is not None:
        print ()
        print_linewrapped (pub.abstract, maxwidth=72)

    app.db.log_action (pub.id, 'visit')


def cmd_ingest (app, argv):
    from .bibtex import import_stream

    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    bibpath = argv[1]

    with io.open (bibpath, 'rt') as f:
        import_stream (app, f)


def cmd_jpage (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    pub = app.locate_or_die (idtext)
    if pub.doi is None:
        die ('cannot open journal website: no DOI for record')

    app.db.log_action (pub.id, 'visit')
    app.open_url ('http://dx.doi.org/' + wu.urlquote (pub.doi))


def cmd_list (app, argv):
    if len (argv) < 2:
        raise UsageError ('expected arguments')

    print_generic_listing (app.db, app.locate_pubs (argv[1:], noneok=True))


def cmd_pdfpath (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]
    pub = app.locate_or_die (idtext)

    sha1 = app.db.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid = ?', pub.id)
    if sha1 is None:
        # XXX: only do this optionally, maybe?
        sha1 = app.try_get_pdf (pub)

    if sha1 is not None:
        print (libpath (sha1, 'pdf'))

    # simply print nothing if no PDF available.


def cmd_read (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    pub = app.locate_or_die (idtext, autolearn=True)

    sha1 = app.db.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid = ?', pub.id)
    if sha1 is None:
        sha1 = app.try_get_pdf (pub)

    if sha1 is None:
        die ('no saved PDF for %s, and cannot figure out how to download it', idtext)

    app.db.log_action (pub.id, 'read')
    pdfreader = app.cfg.get_or_die ('apps', 'pdf-reader')
    launch_background_silent (pdfreader, [pdfreader, libpath (sha1, 'pdf')])


def cmd_recent (app, argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    pubs = app.db.pub_fquery ('SELECT DISTINCT p.* FROM pubs AS p, history AS h '
                              'WHERE p.id == h.pubid ORDER BY date DESC LIMIT 10')
    print_generic_listing (app.db, pubs, sort=None)


def cmd_refgrep (app, argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly one argument')

    refkey = argv[1]

    for pub in app.db.pub_query ('refdata NOT NULL'):
        rd = json.loads (pub.refdata)
        val = rd.get (refkey)

        if val is not None:
            print (val)


def cmd_rq (app, argv):
    from .ads import search_ads

    # XXX need a real option-parsing setup
    rawmode = pop_option ('raw', argv)

    if len (argv) < 2:
        raise UsageError ('expected arguments')

    search_ads (app, parse_search (argv[1:]), raw=rawmode)


def cmd_rsbackup (app, argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    app.rsync_backup ()


def cmd_setpdf (app, argv):
    if len (argv) != 3:
        raise UsageError ('expected exactly 2 arguments')

    idtext = argv[1]
    pdfpath = argv[2]

    import hashlib, shutil

    pub = app.locate_or_die (idtext)

    # Get SHA1 of the PDF -- we could be more efficient by copying
    # to a temporary path whil we're at it, but, meh.

    with io.open (pdfpath, 'rb') as f:
        s = hashlib.sha1 ()

        while True:
            b = f.read (4096)
            if not len (b):
                break

            s.update (b)

        sha1 = s.hexdigest ()

    # Copy it into the library
    ensure_libpath_exists (sha1)
    dest = libpath (sha1, 'pdf')
    shutil.copyfile (pdfpath, dest)

    # Update the DB
    app.db.execute ('INSERT OR REPLACE INTO pdfs VALUES (?, ?)', (sha1, pub.id))


def cmd_setsecret (app, argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    # Note that we've wrapped sys.stdin inside a UTF-8 decoder, so we have to
    # check the true underlying stream.
    if not sys.stdin.stream.isatty ():
        die ('this command can only be run with standard input set to a TTY')

    from .secret import store_user_secret
    store_user_secret (app.cfg)


# Toplevel driver infrastructure

def usage ():
    print ('usage goes here')


def driver (argv=None):
    if argv is None:
        argv = sys.argv

    if len (argv) == 1 or argv[1] == '--help':
        usage ()
        return

    cmdname = argv[1]
    cmdfunc = globals ().get ('cmd_' + cmdname.replace ('-', '_'))

    if not callable (cmdfunc):
        die ('"%s" is not a recognized subcommand; run me without '
             'arguments for usage help', cmdname)

    from . import BibApp

    with BibApp () as app:
        try:
            cmdfunc (app, argv[1:])
        except UsageError as ue:
            # TODO: synopsize command-specific usage help as an attribute on the
            # function (so we can auto-gen a multi-command usage summary too)
            raise SystemExit ('usage error: ' + ue.bibmsg)

    return 0


if __name__ == '__main__':
    driver ()
