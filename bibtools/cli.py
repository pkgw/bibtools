# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
The command-line interface.
"""

__all__ = ['driver']

from .util import *
from . import *
from .bibcore import print_generic_listing, parse_search


def cmd_ads (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        pub = db.locate_or_die (idtext)
        if pub.bibcode is None:
            die ('cannot open ADS for this publication: no bibcode on record')

        db.log_action (pub.id, 'visit')
        open_url ('http://labs.adsabs.harvard.edu/adsabs/abs/' + urlquote (pub.bibcode))


def cmd_apage (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        pub = db.locate_or_die (idtext)
        if pub.arxiv is None:
            die ('cannot open arxiv website: no identifier for record')

        db.log_action (pub.id, 'visit')
        open_url ('http://arxiv.org/abs/' + urlquote (pub.arxiv))


def cmd_btexport (argv):
    from bibtex import bibtex_styles, bibtexify_one, write_bibtexified

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

    for line in open (auxfile):
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

    # Export

    seenids = {}
    first = True
    write = sys.stdout.write

    with connect () as db:
        for nick in sorted (citednicks):
            curs = db.pub_fquery ('SELECT p.* FROM pubs AS p, nicknames AS n '
                                  'WHERE p.id == n.pubid AND n.nickname == ?', nick)
            res = list (curs)

            if not len (res):
                die ('citation to unrecognized nickname "%s"', nick)
            if len (res) != 1:
                die ('cant-happen multiple matches for nickname "%s"', nick)

            pub = res[0]

            if pub.id in seenids:
                die ('"%s" and "%s" refer to the same publication; this will '
                     'cause duplicate entries', nick, seenids[pub.id])

            if pub.refdata is None:
                die ('no reference data for "%s"', nick)

            seenids[pub.id] = nick

            if first:
                first = False
            else:
                write ('\n')

            bt = bibtexify_one (db, style, pub)
            bt['_ident'] = nick
            write_bibtexified (write, bt)


def cmd_canon_journal (argv):
    if len (argv) not in (3, 4):
        raise UsageError ('expected 2 or 3 arguments')

    oldjournal = argv[1]
    newjournal = argv[2]
    newissn = argv[3] if len (argv) > 3 else None

    with connect () as db:
        for pub in db.pub_query ('refdata NOT NULL'):
            rd = json.loads (pub.refdata)
            if rd.get ('journal', '') != oldjournal:
                continue

            rd['journal'] = newjournal

            if 'issn' not in rd and newissn is not None:
                rd['issn'] = newissn

            db.execute ('UPDATE pubs SET refdata = ? WHERE id == ?',
                        (json.dumps (rd), pub.id))


def cmd_delete (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        # TODO: mode to match multiple publications and delete them
        # all, if a --force flag is given.
        pub = db.locate_or_die (idtext, autolearn=True)
        db.delete_pub (pub.id)


def cmd_edit (argv):
    from . import textfmt

    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    import tempfile
    idtext = argv[1]

    with connect () as db:
        pub = db.locate_or_die (idtext, autolearn=True)

        work = tempfile.NamedTemporaryFile (prefix='bib.edit.', dir='.', delete=False)
        enc = codecs.getwriter ('utf-8') (work)
        textfmt.text_export_one (db, pub, enc.write, 72)
        work.close ()

        run_editor (work.name)

        enc = codecs.getreader ('utf-8') (open (work.name))
        info = textfmt.text_import_one (enc)
        db.update_pub (pub, info)

        try:
            os.unlink (work.name)
        except Exception as e:
            warn ('couldn\'t delete temporary file "%s": %s', work.name, e)

        try:
            os.unlink (work.name + '~')
        except:
            pass # whatever.


def cmd_init (argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    mkdir_p (bibpath ())

    if os.path.exists (dbpath):
        die ('the file "%s" already exists', dbpath)

    with connect () as db:
        try:
            init = datastream ('schema.sql').read ()
            db.executescript (init)
        except sqlite3.OperationalError as e:
            die ('cannot initialize "%s": %s', dbpath, e)


def cmd_info (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        # TODO: should be OK to match multiple publications and print them all
        # out.

        pub = db.locate_or_die (idtext, autolearn=True)

        year = pub.year or 'no year'
        title = pub.title or '(no title)'

        authors = list (db.get_pub_authors (pub.id))
        if len (authors):
            authstr = ', '.join (a[1] for a in authors)
        else:
            authstr = '(no authors)'

        print title
        print authstr, '(%s)' % year

        if pub.arxiv is not None:
            print 'arxiv:', pub.arxiv
        if pub.bibcode is not None:
            print 'bibcode:', pub.bibcode
        if pub.doi is not None:
            print 'DOI:', pub.doi
        if pub.refdata is not None:
            rd = json.loads (pub.refdata)
            print '~BibTeX: @%s {' % rd.pop ('_type'),
            bits = ('%s="%s"' % t
                    for t in sorted (rd.iteritems (), key=lambda t: t[0]))
            print u', '.join (bits).encode ('utf-8'), '}'

        if pub.abstract is not None:
            print
            print_linewrapped (pub.abstract, maxwidth=72)

        db.log_action (pub.id, 'visit')


_bibtex_replacements = (
    '\\&ap;', u'~',
    '\\&#177;', u'±',
    '\&gt;~', u'⪞',
    '\&lt;~', u'⪝',
    '{', u'',
    '}', u'',
    '<SUP>', u'^',
    '</SUP>', u'',
    '<SUB>', u'_',
    '</SUB>', u'',
    'Delta', u'Δ',
    'Omega', u'Ω',
    '( ', u'(',
    ' )', u')',
    '[ ', u'[',
    ' ]', u']',
    ' ,', u',',
    ' .', u'.',
    ' ;', u';',
    '\t', u' ',
    '  ', u' ',
)

def _fix_bibtex (text):
    """Ugggghhh. So many problems."""

    if text is None:
        return None

    text = unicode (text)

    for i in xrange (0, len (_bibtex_replacements), 2):
        text = text.replace (_bibtex_replacements[i], _bibtex_replacements[i+1])
    return text


def sniff_url (url):
    from urllib2 import unquote

    p = 'http://dx.doi.org/'
    if url.startswith (p):
        return 'doi', unquote (url[len (p):])

    p = 'http://adsabs.harvard.edu/cgi-bin/nph-bib_query?bibcode='
    if url.startswith (p):
        return 'bibcode', unquote (url[len (p):])

    p = 'http://labs.adsabs.harvard.edu/ui/abs/'
    if url.startswith (p):
        return 'bibcode', unquote (url[len (p):])

    p = 'http://arxiv.org/abs/'
    if url.startswith (p):
        return 'arxiv', unquote (url[len (p):])

    p = 'http://arxiv.org/pdf/'
    if url.startswith (p):
        return 'arxiv', unquote (url[len (p):])

    return None, None


def _ingest_one (db, rec):
    abstract = rec.get ('abstract')
    arxiv = rec.get ('eprint')
    bibcode = rec.get ('bibcode')
    doi = rec.get ('doi')
    nickname = rec.get ('id')
    title = rec.get ('title')
    year = rec.get ('year')

    if year is not None:
        year = int (year)

    if 'author' in rec:
        authors = [_translate_bibtex_name (_fix_bibtex (a)) for a in rec['author']]
    else:
        authors = None

    if 'editor' in rec:
        # for some reason bibtexparser's editor() and author() filters work
        # differently.
        editors = [_translate_bibtex_name (_fix_bibtex (e['name'])) for e in rec['editor']]
    else:
        editors = None

    abstract = _fix_bibtex (abstract)
    title = _fix_bibtex (title)

    # Augment information with what we can get from URLs

    urlinfo = []

    if 'url' in rec:
        urlinfo.append (sniff_url (rec['url']))

    for k, v in rec.iteritems ():
        if k.startswith ('citeulike-linkout-'):
            urlinfo.append (sniff_url (v))

    for kind, info in urlinfo:
        if kind is None:
            continue

        if kind == 'bibcode' and bibcode is None:
            bibcode = info

        if kind == 'doi' and doi is None:
            doi = info

        if kind == 'arxiv' and arxiv is None:
            arxiv = info

    # Shape up missing bibcodes
    # XXX: deactivated since I've embedded everything I can in the original file
    #if bibcode is None and doi is not None:
    #    bibcode = doi_to_maybe_bibcode (doi)
    #    print 'mapped', doi, 'to', bibcode or '(lookup failed)'

    # Gather reference information
    # TO DO: normalize journal name, pages...

    refdata = {'_type': rec['type']}

    for k, v in rec.iteritems ():
        if k in ('type', 'id', 'abstract', 'archiveprefix', 'author',
                 'bibcode', 'day', 'doi', 'editor', 'eprint', 'keyword',
                 'keywords', 'link', 'month', 'posted-at', 'pmid',
                 'priority', 'title', 'url', 'year'):
            continue
        if k.startswith ('citeulike'):
            continue
        refdata[k] = v

    # Ready to insert.

    info = dict (abstract=abstract, arxiv=arxiv, authors=authors,
                 bibcode=bibcode, doi=doi, editors=editors,
                 nicknames=[nickname], refdata=refdata, title=title, year=year)
    db.learn_pub (info)


def cmd_ingest (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    bibpath = argv[1]
    from .hacked_bibtexparser.bparser import BibTexParser
    from .hacked_bibtexparser.customization import author, editor, type, convert_to_unicode

    custom = lambda r: editor (author (type (convert_to_unicode (r))))

    with open (bibpath) as bibfile, connect () as db:
        bp = BibTexParser (bibfile, customization=custom)

        for rec in bp.get_entry_list ():
            _ingest_one (db, rec)


def cmd_jpage (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        pub = db.locate_or_die (idtext)
        if pub.doi is None:
            die ('cannot open journal website: no DOI for record')

        db.log_action (pub.id, 'visit')
        open_url ('http://dx.doi.org/' + urlquote (pub.doi))


def _list_cmd_add (db, argv):
    if len (argv) < 3:
        raise UsageError ('expected at least 2 arguments')

    listname = argv[1]
    # FIXME: check listname to avoid "bib list add abc+12 xyz+10" mistake
    dblistname = 'user_' + listname

    try:
        for pub in db.locate_pubs (argv[2:], autolearn=True):
            db.execute ('INSERT OR IGNORE INTO publists VALUES (?, '
                        '  (SELECT ifnull(max(idx)+1,0) FROM publists WHERE name == ?), '
                        '?)', (dblistname, dblistname, pub.id))
    except Exception as e:
        die (e)


def _list_cmd_rm (db, argv):
    if len (argv) < 3:
        raise UsageError ('expected at least 2 arguments')

    listname = argv[1]
    # FIXME: check listname to avoid "bib list add abc+12 xyz+10" mistake
    dblistname = 'user_' + listname

    # We want to complain if an individual term doesn't match anything in the
    # list, but if the user specifies "williams.*" and we get a bunch of hits
    # only one of which is in the list, that's OK. So we need to process terms
    # individually.

    c = db.cursor ()

    try:
        for idtext in argv[2:]:
            ndeleted = 0

            for pub in db.locate_pubs ((idtext,)):
                c.execute ('DELETE FROM publists WHERE name == ? AND pubid == ?',
                           (dblistname, pub.id))
                ndeleted += c.rowcount

            if not ndeleted:
                warn ('no entries in "%s" matched "%s"', listname, idtext)
    except Exception as e:
        die (e)


def _list_cmd_summ (db, argv):
    if len (argv) != 2:
        raise UsageError ('expected one argument')

    listname = argv[1]
    # FIXME: check listname to avoid "bib list add abc+12 xyz+10" mistake
    dblistname = 'user_' + listname

    q = db.pub_fquery ('SELECT p.* FROM pubs AS p, publists AS pl '
                       'WHERE p.id == pl.pubid AND pl.name == ? '
                       'ORDER BY pl.idx', (dblistname))
    print_generic_listing (db, q)


def cmd_list (argv):
    if len (argv) < 2:
        raise UsageError ('"list" requires a subcommand')

    subcmd = argv[1]
    subfunc = globals ().get ('_list_cmd_' + subcmd.replace ('-', '_'))

    if not callable (subfunc):
        die ('"%s" is not a recognized subcommand of "list"; run me without '
             'arguments for usage help', subcmd)

    with connect () as db:
        subfunc (db, argv[1:])


def cmd_read (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly 1 argument')

    idtext = argv[1]

    with connect () as db:
        pub = db.locate_or_die (idtext, autolearn=True)

        sha1 = db.getfirstval ('SELECT sha1 FROM pdfs WHERE pubid = ?', pub.id)
        if sha1 is None:
            proxy = get_proxy_or_die ()
            sha1 = db.try_get_pdf_for_id (proxy, pub.id)

        if sha1 is not None:
            # no big deal if we fail later
            db.log_action (pub.id, 'read')

    if sha1 is None:
        die ('no saved PDF for %s, and cannot figure out how to download it', idtext)

    pdfreader = BibConfig ().get_or_die ('apps', 'pdf-reader')
    launch_background_silent (pdfreader, [pdfreader, libpath (sha1, 'pdf')])


def cmd_recent (argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    with connect () as db:
        print_generic_listing (db, db.pub_fquery ('SELECT DISTINCT p.* '
                                                  'FROM pubs AS p, history AS h '
                                                  'WHERE p.id == h.pubid '
                                                  'ORDER BY date DESC LIMIT 10'))


def cmd_refgrep (argv):
    if len (argv) != 2:
        raise UsageError ('expected exactly one argument')

    refkey = argv[1]

    with connect () as db:
        for pub in db.pub_query ('refdata NOT NULL'):
            rd = json.loads (pub.refdata)
            val = rd.get (refkey)

            if val is not None:
                print val.encode ('utf-8')


def cmd_rq (argv):
    from .ads import search_ads

    if len (argv) < 2:
        raise UsageError ('expected arguments')

    # XXX need a real option-parsing setup
    rawmode = '--raw' in argv
    if rawmode:
        argv.remove ('--raw')

    search_ads (parse_search (argv[1:]), raw=rawmode)


def cmd_setpdf (argv):
    if len (argv) != 3:
        raise UsageError ('expected exactly 2 arguments')

    idtext = argv[1]
    pdfpath = argv[2]

    import hashlib, shutil

    with connect () as db:
        # Check that we know what pub we're talking about
        pub = db.locate_or_die (idtext)

        # Get SHA1 of the PDF
        with open (pdfpath) as f:
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
        db.execute ('INSERT OR REPLACE INTO pdfs VALUES (?, ?)', (sha1, pub.id))


def cmd_setsecret (argv):
    if len (argv) != 1:
        raise UsageError ('expected no arguments')

    if not sys.stdin.isatty ():
        die ('this command can only be run with standard input set to a TTY')

    store_user_secret ()


def cmd_summ (argv):
    if len (argv) < 2:
        raise UsageError ('expected arguments')

    with connect () as db:
        print_generic_listing (db, db.locate_pubs (argv[1:], noneok=True))


# Toplevel driver infrastructure

def usage ():
    print 'usage goes here'


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

    try:
        cmdfunc (argv[1:])
    except UsageError as ue:
        # TODO: synopsize command-specific usage help as an attribute on the
        # function (so we can auto-gen a multi-command usage summary too)
        raise SystemExit ('usage error: ' + ue.bibmsg)

    return 0


if __name__ == '__main__':
    driver ()
