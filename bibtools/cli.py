# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2015 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
The command-line interface.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import codecs, io, json, os.path, sys
import six
from pwkit.cli import multitool, pop_option

from . import BibError, webutil as wu
from .util import *
from .bibcore import print_generic_listing, parse_search

__all__ = ['driver']


class Btexport (multitool.Command):
    name = 'btexport'
    argspec = '[-i] <output-style> <aux-file>'
    summary = 'Dump BibTeX entries needed for an .aux file.'
    more_help = '''If the "-i" option is provided, missing entries are ignored; if not, the
program exits with an error if any are encountered.'''

    def invoke (self, args, app=None, **kwargs):
        from .bibtex import get_style_or_die, export_to_bibtex

        ignore_missing = pop_option ('i', args)

        if len (args) != 2:
            raise multitool.UsageError ('expected exactly 2 arguments')

        stylename = args[0]
        auxfile = args[1]

        style = get_style_or_die (stylename)

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
        export_to_bibtex (app, style, citednicks, ignore_missing=ignore_missing)


class Btmerge (multitool.Command):
    name = 'btmerge'
    argspec = '<output-style> <bib-file> <aux-file>'
    summary = 'Make BibTeX entries needed for an .aux file, based on an existing BibTeX file.'

    def invoke (self, args, app=None, **kwargs):
        from .bibtex import get_style_or_die, merge_with_bibtex

        if len (args) != 3:
            raise multitool.UsageError ('expected exactly 3 arguments')

        stylename = args[0]
        bibfile = args[1]
        auxfile = args[2]

        style = get_style_or_die (stylename)

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
        merge_with_bibtex (app, bibfile, style, citednicks)


class Btprint (multitool.Command):
    name = 'btprint'
    argspec = '<outstyle> <pub-nicknames...>'
    summary = 'Print BibTeX entries for named publications.'

    def invoke (self, args, app=None, **kwargs):
        from .bibtex import get_style_or_die, export_to_bibtex

        if len (args) < 2:
            raise multitool.UsageError ('expected at least 2 arguments')

        stylename = args[0]
        nicks = args[1:]

        style = get_style_or_die (stylename)

        # That's all there is to it.
        export_to_bibtex (app, style, nicks)


class CanonJournal (multitool.Command):
    name = 'canon-journal'
    argspec = '<old-journal-name> <new-journal-name> [new-journal-ISSN]'
    summary = 'Canonicalize a journal name in the reference data.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) not in (2, 3):
            raise multitool.UsageError ('expected 2 or 3 arguments')

        oldjournal = args[0]
        newjournal = args[1]
        newissn = args[2] if len (args) > 2 else None

        for pub in app.db.pub_query ('refdata NOT NULL'):
            rd = json.loads (pub.refdata)
            if rd.get ('journal', '') != oldjournal:
                continue

            rd['journal'] = newjournal

            if 'issn' not in rd and newissn is not None:
                rd['issn'] = newissn

            app.db.execute ('UPDATE pubs SET refdata = ? WHERE id == ?',
                            (json.dumps (rd), pub.id))


class _Complete (multitool.Command):
    name = '_complete'
    argspec = '{miscellaneous}'
    summary = 'Print completion information for shell integration.'

    def invoke (self, args, app=None, tool=None, **kwargs):
        if len (args) < 1:
            raise multitool.UsageError ('expected at least 1 argument')

        subcommand = args[0]

        from . import completions
        completions.process (app, tool, subcommand, args[1:])


class Delete (multitool.Command):
    name = 'delete'
    argspec = '<pub>'
    summary = 'Delete the record for a publication.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

        # TODO: mode to match multiple publications and delete them
        # all, if a --force flag is given.

        pub = app.locate_or_die (idtext, autolearn=True)
        app.db.delete_pub (pub.id)


class Dump (multitool.Command):
    name = 'dump'
    argspec = ''
    summary = 'Dump the database in a textual backup format.'
    help_if_no_args = False

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 0:
            raise multitool.UsageError ('expected no arguments')

        app.export_all (sys.stdout, 72)


class DumpCrossref (multitool.Command):
    name = 'dump-crossref'
    argspec = '<pub>'
    summary = 'Dump the Crossref XML record for a publication.'

    def invoke (self, args, app=None, **kwargs):
        from pwkit.io import get_stdout_bytes

        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        # Here we have a slight wrinkle from the usual approach. If the argument
        # is a DOI, just fetch it without trying to autolearn a database entry.

        idtext = args[0]

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
        bout = get_stdout_bytes()

        for data in handle:
            bout.write (data)


class Edit (multitool.Command):
    name = 'edit'
    argspec = '<pub>'
    summary = 'Edit a publication\'s record.'

    def invoke (self, args, app=None, **kwargs):
        from . import textfmt

        from tempfile import NamedTemporaryFile

        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

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


class ForgetPDF (multitool.Command):
    name = 'forgetpdf'
    argspec = '<pub>'
    summary = 'Discard information about the publication\'s fulltext PDF.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]
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


class GoAds (multitool.Command):
    name = 'go-ads'
    argspec = '<pub>'
    summary = 'Open the publication\'s ADS abstract page.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        # Here we have a slight wrinkle from the usual approach. If the argument
        # is a bibcode, just fetch it without trying to autolearn a database
        # entry.

        idtext = args[0]

        from .bibcore import classify_pub_ref
        kind, content = classify_pub_ref (idtext)

        if kind == 'bibcode':
            bibcode = content
            # XXX: should log a visit if there's a pub, in this case
        else:
            pub = app.locate_or_die (idtext)
            if pub.bibcode is None:
                die ('cannot open ADS for this publication: no bibcode on record')
            bibcode = pub.bibcode
            app.db.log_action (pub.id, 'visit')

        app.open_url ('http://ui.adsabs.harvard.edu/#abs/%s' % wu.urlquote (bibcode))


class GoArxiv (multitool.Command):
    name = 'go-arxiv'
    argspec = '<pub>'
    summary = 'Open the publication\'s arXiV abstract page.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

        pub = app.locate_or_die (idtext)
        if pub.arxiv is None:
            die ('cannot open arxiv website: no identifier for record')

        app.db.log_action (pub.id, 'visit')
        app.open_url ('http://arxiv.org/abs/' + wu.urlquote (pub.arxiv))


class GoJournal (multitool.Command):
    name = 'go-journal'
    argspec = '<pub>'
    summary = 'Open the journal\'s page for the publication.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

        pub = app.locate_or_die (idtext)
        if pub.doi is None:
            die ('cannot open journal website: no DOI for record')

        app.db.log_action (pub.id, 'visit')
        app.open_url ('http://dx.doi.org/' + wu.urlquote (pub.doi))


class Grep (multitool.Command):
    name = 'grep'
    argspec = '[-i][-f][-r] <pattern>'
    summary = 'Search for text in the bibliographic database.'

    def invoke (self, args, app=None, **kwargs):
        import re

        nocase = pop_option ('i', args)
        fixed = pop_option ('f', args)
        refinfo = pop_option ('r', args)

        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 non-option argument')

        regex = args[0]

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


class Group (multitool.DelegatingCommand):
    name = 'group'
    summary = 'Operate on groups of publications.'

    class Add (multitool.Command):
        name = 'add'
        argspec = '<group> <pubs...>'
        summary = 'Add publications to a group.'

        def invoke (self, args, app=None, **kwargs):
            if len (args) < 2:
                raise multitool.UsageError ('expected at least 2 arguments')

            groupname = args[0]
            # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
            dbgroupname = 'user_' + groupname

            try:
                for pub in app.locate_pubs (args[1:], autolearn=True):
                    app.db.execute ('INSERT OR IGNORE INTO publists VALUES (?, '
                                    '  (SELECT ifnull(max(idx)+1,0) FROM publists WHERE name == ?), '
                                    '?)', (dbgroupname, dbgroupname, pub.id))
            except Exception as e:
                die (e)


    class List (multitool.Command):
        name = 'list'
        argspec = '[group]'
        summary = 'List all of the groups, or the publications in a group.'
        help_if_no_args = False

        def invoke (self, args, app=None, **kwargs):
            if len (args) not in (0, 1):
                raise multitool.UsageError ('expected 0 or 1 arguments')

            try:
                if len (args) == 0:
                    # List the groups.
                    q = app.db.execute ('SELECT DISTINCT name FROM publists WHERE '
                                        'name LIKE ? ORDER BY name ASC', ('user_%', ))
                    for (name, ) in q:
                        print (name[5:])
                else:
                    # List the items in a group.
                    groupname = args[0]
                    # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
                    dbgroupname = 'user_' + groupname

                    q = app.db.pub_fquery ('SELECT p.* FROM pubs AS p, publists AS pl '
                                           'WHERE p.id == pl.pubid AND pl.name == ? '
                                           'ORDER BY pl.idx', dbgroupname)
                    print_generic_listing (app.db, q)
            except Exception as e:
                die (e)


    class Rm (multitool.Command):
        name = 'rm'
        argspec = '<group> <pubs...>'
        summary = 'Remove publications from a group.'

        def invoke (self, args, app=None, **kwargs):
            if len (args) < 2:
                raise multitool.UsageError ('expected at least 2 arguments')

            groupname = args[0]
            # FIXME: check groupname to avoid "bib group add abc+12 xyz+10" mistake
            dbgroupname = 'user_' + groupname

            # We want to complain if an individual term doesn't match anything in the
            # group, but if the user specifies "williams.*" and we get a bunch of hits
            # only one of which is in the group, that's OK. So we need to process terms
            # individually.

            c = app.db.cursor ()

            try:
                for idtext in args[1:]:
                    ndeleted = 0

                    for pub in app.locate_pubs ((idtext,)):
                        c.execute ('DELETE FROM publists WHERE name == ? AND pubid == ?',
                                   (dbgroupname, pub.id))
                        ndeleted += c.rowcount

                    if not ndeleted:
                        warn ('no entries in "%s" matched "%s"', groupname, idtext)
            except Exception as e:
                die (e)


class Igrep (multitool.Command):
    name = 'igrep'
    argspec = '<output-style> <pattern>'
    summary = 'Search for ISSNs in journal-name/ISSN tables.'

    def invoke (self, args, app=None, **kwargs):
        import re
        from .bibtex import get_style_or_die

        if len (args) != 2:
            raise multitool.UsageError ('expected exactly 2 non-option arguments')

        stylename = args[0]
        regex = args[1].encode('utf8')

        style = get_style_or_die (stylename)
        comp = re.compile (regex, re.IGNORECASE)

        inm = getattr (style, 'issn_name_map', None)
        if inm is None:
            die ('style "%s" does not provide an ISSN/journal-name map', stylename)

        # t = (issn, jname):
        matches = (t for t in six.viewitems (inm)
                   if comp.search (t[1]) is not None)

        for issn, jname in sorted (matches, key=lambda t: t[0]):
            print ('%s %s' % (issn, jname.decode('utf8')))


class Init (multitool.Command):
    name = 'init'
    argspec = ''
    summary = 'Initialize the publication database.'
    help_if_no_args = False

    def invoke (self, args, app=None, **kwargs):
        from .db import init

        if len (args) != 0:
            raise multitool.UsageError ('expected no arguments')

        init (app)


class Info (multitool.Command):
    name = 'info'
    argspec = '<pub>'
    summary = 'Print information about a publication.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

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
            bits = (fmt (t) for t in sorted (rd.items (), key=lambda t: t[0]))
            txt += ', '.join (bits) + '}'
            print_linewrapped (txt, rest_prefix='   ')

        if pub.abstract is not None:
            print ()
            print_linewrapped (pub.abstract, maxwidth=72)

        app.db.log_action (pub.id, 'visit')


class Ingest (multitool.Command):
    name = 'ingest'
    argspec = '<bibtex-file>'
    summary = 'Ingest information from a BibTeX file.'

    def invoke (self, args, app=None, **kwargs):
        from .bibtex import import_stream

        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        bibpath = args[0]

        with io.open (bibpath, 'rt') as f:
            import_stream (app, f)


class List (multitool.Command):
    name = 'list'
    argspec = '<pubs...>'
    summary = 'List publications in the database.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) < 1:
            raise multitool.UsageError ('expected arguments')

        print_generic_listing (app.db, app.locate_pubs (args, noneok=True))


class Pdfpath (multitool.Command):
    name = 'pdfpath'
    argspec = '<pub>'
    summary = 'Print the path to a publication\'s saved full-text PDF.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]
        pub = app.locate_or_die (idtext)

        sha1 = app.db.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid = ?', pub.id)
        if sha1 is None:
            # XXX: only do this optionally, maybe?
            sha1 = app.try_get_pdf (pub)

        if sha1 is not None:
            print (libpath (sha1, 'pdf'))

        # simply print nothing if no PDF available.


class Read (multitool.Command):
    name = 'read'
    argspec = '<pub>'
    summary = 'Open a publication\'s PDF.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 1:
            raise multitool.UsageError ('expected exactly 1 argument')

        idtext = args[0]

        pub = app.locate_or_die (idtext, autolearn=True)

        sha1 = app.db.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid = ?', pub.id)
        if sha1 is None:
            sha1 = app.try_get_pdf (pub)

        if sha1 is None:
            die ('no saved PDF for %s, and cannot figure out how to download it', idtext)

        app.db.log_action (pub.id, 'read')
        pdfreader = app.cfg.get_or_die ('apps', 'pdf-reader')
        launch_background_silent (pdfreader, [pdfreader, libpath (sha1, 'pdf')])


class Recent (multitool.Command):
    name = 'recent'
    argspec = ''
    summary = 'List recently-accessed publications.'
    help_if_no_args = False

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 0:
            raise multitool.UsageError ('expected no arguments')

        pubs = app.db.pub_fquery ('SELECT DISTINCT p.* FROM pubs AS p, history AS h '
                                  'WHERE p.id == h.pubid ORDER BY date DESC LIMIT 10')
        print_generic_listing (app.db, pubs, sort=None)


class Rq (multitool.Command):
    name = 'rq'
    argspec = '[-l] <search terms...>'
    summary = 'Query a remote bibliographic database.'
    more_help = '''Currently only supports two terms: author surname and publication year. A
leading caret (^) searches for first author only. Years less than 100 are
handled intelligently. For example:

   bib rq ^williams 14

Will search for papers with first author surname "williams"
(case-insensitively) from the year 2014.

The "-l" option causes a longer listing to be generated in case there are many
matches.

There is also a "--raw" option for debugging the output of the ADS search API.
'''

    def invoke (self, args, app=None, **kwargs):
        from .ads import search_ads

        # XXX need a real option-parsing setup
        rawmode = pop_option ('raw', args)
        large = pop_option ('l', args)

        if len (args) < 1:
            raise multitool.UsageError ('expected arguments')

        search_ads (app, parse_search (args), raw=rawmode, large=large)


class Rsbackup (multitool.Command):
    name = 'rsbackup'
    argspec = ''
    summary = 'Back up the database via rsync.'
    help_if_no_args = False

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 0:
            raise multitool.UsageError ('expected no arguments')

        app.rsync_backup ()


class Setpdf (multitool.Command):
    name = 'setpdf'
    argspec = '<pub> <pdf-path>'
    summary = 'Manually specify the full-text PDF file for a publication.'

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 2:
            raise multitool.UsageError ('expected exactly 2 arguments')

        idtext = args[0]
        pdfpath = args[1]

        import hashlib, shutil

        pub = app.locate_or_die (idtext)

        # Get SHA1 of the PDF -- we could be more efficient by copying
        # to a temporary path while we're at it, but, meh.

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


class Setsecret (multitool.Command):
    name = 'setsecret'
    argspec = ''
    summary = 'Set the secret used to gain access to full-text articles.'
    help_if_no_args = False

    def invoke (self, args, app=None, **kwargs):
        if len (args) != 0:
            raise multitool.UsageError ('expected no arguments')

        # Note that we've wrapped sys.stdin inside a UTF-8 decoder, so we have to
        # check the true underlying stream.
        if not sys.stdin.stream.isatty ():
            die ('this command can only be run with standard input set to a TTY')

        from .secret import store_user_secret
        store_user_secret (app.cfg)


# Toplevel driver infrastructure

HelpCommand = multitool.HelpCommand

class Bibtool (multitool.Multitool):
    cli_name = 'bib'
    summary = 'Manage your bibliography.'

    def invoke_command (self, cmd, args, app=None, **kwargs):
        from . import BibApp

        with BibApp () as app:
            super (Bibtool, self).invoke_command (cmd, args, app=app, **kwargs)

def commandline ():
    multitool.invoke_tool (globals ())
