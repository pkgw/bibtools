# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Various utilities, mostly generic.
"""

from __future__ import absolute_import, division, print_function, unicode_literals
from six import text_type

import errno, io, os.path, re, sys


# Generic things

__all__ = ('die warn reraise_context squish_spaces mkdir_p').split ()


def die (fmt, *args):
    if not len (args):
        raise SystemExit ('error: ' + text_type (fmt))
    raise SystemExit ('error: ' + fmt % args)


def warn (fmt, *args):
    if not len (args):
        print ('warning:', fmt, file=sys.stderr)
    else:
        print ('warning:', fmt % args, file=sys.stderr)


def reraise_context (fmt, *args):
    if len (args):
        cstr = fmt % args
    else:
        cstr = text_type (fmt)

    ex = sys.exc_info ()[1]
    if len (ex.args):
        cstr = '%s: %s' % (cstr, ex.args[0])
    ex.args = (cstr, ) + ex.args[1:]
    raise


_whitespace_re = re.compile (r'\s+')

def squish_spaces (text):
    if text is None:
        return None
    return _whitespace_re.sub (' ', text).strip ()


def mkdir_p (path):
    """That is, create `path` as a directory and all of its parents, ignoring
    errors if they already exist."""

    try:
        os.makedirs (path)
    except OSError as e:
        if e.errno != errno.EEXIST or not os.path.isdir (path):
            raise


# More app-specific

__all__ += ('datastream bibpath libpath ensure_libpath_exists').split ()

def datastream (name):
    from pkg_resources import Requirement, resource_stream
    return resource_stream (Requirement.parse ('bibtools'),
                            'bibtools/' + name)


def _make_user_data_pather ():
    datadir = os.environ.get ('XDG_DATA_HOME',
                              os.path.expanduser ('~/.local/share'))

    def pathfunc (*args):
        return os.path.join (datadir, 'bib', *args)

    return pathfunc


bibpath = _make_user_data_pather ()


def libpath (sha1, ext):
    return bibpath ('lib', sha1[:2], sha1[2:] + '.' + ext)


def ensure_libpath_exists (sha1):
    mkdir_p (bibpath ('lib', sha1[:2]))


# Running programs

__all__ += ('launch_background_silent open_url run_editor').split ()

def launch_background_silent (cmd, argv):
    """Launch a process in the background, with its input and output redirected to
    /dev/null. execlp() is used, so that `cmd` is searched for in $PATH. `argv` is
    named with intent; `argv[0]` is the self-name of `cmd`, not the first extra
    argument.

    This function returns!

    This is intended for launching GUI programs from a terminal, where we don't
    want to wait for them or see their inane warnings.
    """

    import resource

    try:
        pid = os.fork ()
    except OSError as e:
        die ('cannot fork() first time (to launch %s): %s', cmd, e)

    if pid != 0:
        return # parent is done

    # We're the first forked child.
    os.setsid () # become new session leader, apparently a good thing to do.

    try:
        pid2 = os.fork ()
    except OSError as e:
        die ('cannot fork() second time (to launch %s): %s', cmd, e)

    if pid2 != 0:
        os._exit (0) # this child is done

    # The second forked child actually exec()s the program.
    nullin = io.open (os.devnull, 'rb')
    os.dup2 (nullin.fileno (), 0)
    nullout = io.open (os.devnull, 'wb')
    os.dup2 (nullout.fileno (), 1)
    os.dup2 (nullout.fileno (), 2)
    os.closerange (3, resource.getrlimit (resource.RLIMIT_NOFILE)[0])
    os.execlp (cmd, *argv)


def open_url (app, url):
    """Opens up the URL in some GUI program and returns.

    Python has a `webbrowser` module that does this, but my Firefox
    prints out a few warnings when you launch it and I really want
    to make those disappear."""

    opener = app.cfg.get_or_die ('apps', 'url-opener')
    launch_background_silent (opener, [opener, url])


def run_editor (path):
    """Open up a text editor with the specified path and wait for it to exit."""
    import subprocess

    editor = os.environ.get ('VISUAL')
    if editor is None:
        editor = os.environ.get ('EDITOR')
    if editor is None:
        editor = 'vi'

    rv = subprocess.call ([editor, path], close_fds=True, shell=False)
    if rv:
        die ('editor for file "%s" exited with an error', path)


# Terminal tomfoolery

__all__ += ('get_color_codes set_terminal_echo get_term_width print_linewrapped '
            'print_truncated').split ()

_colors = {
    'none': '',
    'reset': '\033[m',
    'bold': '\033[1m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'bold-red': '\033[1;31m',
    'bold-green': '\033[1;32m',
    'bold-yellow': '\033[1;33m',
    'bold-blue': '\033[1;34m',
    'bold-magenta': '\033[1;35m',
    'bold-cyan': '\033[1;36m',
    # Could add background colors, etc, but these should hold us for now.
}

_emit_color_codes = None

def get_color_codes (stream, *colornames):
    # Right now, if this function is called for various streams, only the one
    # passed in the first call matters. This is a little busted, but I have
    # trouble imagining a situation where it will actually matter.
    global _emit_color_codes

    if _emit_color_codes is None:
        if stream is None:
            stream = sys.stdout

        s = stream
        if hasattr (s, 'stream'):
            # Transparently handle codec wrappers. Not sure of the best way to
            # generically check for them, but this'll do for now.
            s = s.stream

        # XXX: better check, esp. being paged to less.
        _emit_color_codes = s.isatty ()

    if not _emit_color_codes:
        return [''] * len (colornames)

    codes = []

    for cn in colornames:
        if cn is None:
            codes.append ('')
        else:
            cc = _colors.get (cn)
            if cc is None:
                raise Exception ('unknown color name "%s"' % cn)
            codes.append (cc)

    return codes


def set_terminal_echo (tstream, enabled):
    import termios

    if hasattr (tstream, 'stream'):
        # Transparently handle a codec wrapper. Not sure of the best way to
        # generically check for wrapper streams, but this'll do for now.
        return set_terminal_echo (tstream.stream, enabled)

    fd = tstream.fileno ()
    ifl, ofl, cfl, lfl, isp, osp, cc = termios.tcgetattr (fd)

    if enabled:
        lfl |= termios.ECHO
    else:
        lfl &= ~termios.ECHO

    termios.tcsetattr (fd, termios.TCSANOW,
                       [ifl, ofl, cfl, lfl, isp, osp, cc])


def get_term_width (tstream):
    """If tstream is a terminal, use an ioctl to determine the width. If that
    fails but $COLUMNS is set, use that. Otherwise, if we're on a TTY, use a
    width of 80; if we're not, use -1, i.e. no linewrapping. I think this is
    DTRT-logic."""

    import sys, os, termios
    from fcntl import ioctl
    from struct import unpack

    if hasattr (tstream, 'stream'):
        # Transparently handle a codec wrapper. Not sure of the best way to
        # generically check for wrapper streams, but this'll do for now.
        return get_term_width (tstream.stream)

    w = None

    if tstream.isatty ():
        try:
            return unpack (b'hh', ioctl (tstream.fileno (), termios.TIOCGWINSZ, b'....'))[1]
        except:
            pass

    try:
        return int (os.environ['COLUMNS'])
    except:
        pass

    if tstream.isatty ():
        return 80

    return -1


def print_linewrapped (text, maxwidth=None, width=None, stream=None, rest_prefix=''):
    """We assume that spaces within `text` are fungible.

    We're not aware of terminal escape sequences (e.g., things to set colors),
    so in some situations we'll wrap over-aggressively.

    """
    if stream is None:
        stream = sys.stdout

    if width is None:
        w = get_term_width (stream)
    else:
        w = width

    if maxwidth is not None and w > maxwidth:
        # This intentionally doesn't apply if w < 0.
        w = maxwidth

    first = True
    write = stream.write

    if w < 0:
        ofs = 1

        for match in re.finditer (r'\S+', text):
            if first:
                first = False
            else:
                write (' ')
            write (match.group (0))
    else:
        ofs = 0

        for match in re.finditer (r'\S+', text):
            word = match.group (0)
            n = len (word)

            if ofs + 1 + n > w:
                if ofs > 0:
                    write ('\n')
                    write (rest_prefix)
                write (word)
                ofs = n + len (rest_prefix)
            elif first:
                first = False
                write (word)
                ofs = n
            else:
                write (' ')
                write (word)
                ofs = ofs + 1 + n

    if ofs > 0:
        write ('\n')


def print_truncated (text, curofs, stream=None, color=None):
    """We assume that spaces within `text` are fungible.

    We take a `color` argument because otherwise we might truncate a "reset
    color" ANSI command!

    """
    if stream is None:
        stream = sys.stdout

    w = get_term_width (stream)
    write = stream.write

    cc, reset = get_color_codes (stream, color, 'reset')
    write (cc)

    if w < 0 or curofs + len (text) < w:
        write (text)
        write (reset)
        write ('\n')
        return

    # Note that if we have sufficiently little room, we'll just print the
    # ellipsis and no actual words.

    w -= 4 # account for " ..."
    first = True

    for match in re.finditer (r'\S+', text):
        word = match.group (0)
        n = len (word)

        if first:
            first = False

            if curofs + n > w:
                break

            write (word)
            curofs += n
        else:
            if curofs + n + 1 > w:
                break

            write (' ')
            write (word)
            curofs += n + 1

    if not first:
        write (' ')
    write ('...')
    write (reset)
    write ('\n')
