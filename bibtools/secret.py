# -*- mode: python; coding: utf-8 -*-
# Copyright 2014 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""Handling of the user's login secret.

I've made the decision to store this on disk without requiring user input to
access the secret -- i.e., this is what Firefox does for user website
passwords when a Master Password hasn't been enabled. I feel sketchy about
this, but if Mozilla is OK with it, then so am I.

I follow what I believe to be Firefox's storage strategy, which is to use
symmetric encryption to store the secret on disk, with the relevant encryption
keys also stored on disk. Obviously this only provides security against a
completely unmotivated attacker, but it prevents accidental disclosure, and
again, this approach seems to be good enough for Mozilla.

There are crypto modules for Python, but the examples I saw were lengthy and
the modules aren't preinstalled on my computer (therefore most people probably
don't have them), so I've farmed out the work to the openssl CLI.

Because we're in Python, I'm sure that we're doing all sorts of unfortunate
things like keeping the decrypted secret in memory for too long, etc.

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import io, os, random, string, subprocess

from .util import bibpath, set_terminal_echo

__all__ = ('load_user_secret store_user_secret').split ()


def _load_secret_keys ():
    key = iv = None

    with io.open (bibpath ('secret.key'), 'rt') as kfile:
        for line in kfile:
            line = line.strip ()

            if line.startswith ('key='):
                key = line[4:]
            elif line.startswith ('iv ='):
                iv = line[4:]

    if key is None or iv is None:
        die ('damaged secret key file %s?', bibpath ('secret.key'))

    return key, iv


def store_user_secret (cfg):
    openssl = cfg.get_or_die ('apps', 'openssl')

    # Generate a random password for the key generation. Python SystemRandom
    # uses /dev/urandom, so it's possible that the password may be derived
    # in a low-entropy state, but ... meh.

    sysrand = random.SystemRandom ()
    pool = string.digits + string.letters + string.punctuation
    keypass = ''.join (sysrand.choice (pool) for _ in range (64))

    # Generate the static keys

    os.umask (0o177)

    kfd = os.open (bibpath ('secret.key'),
                   os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                   0o600) # just in case ...

    with io.open (kfd, 'wt') as kfile:
        subprocess.check_call ([openssl, 'enc', '-aes-256-cbc', '-k', keypass,
                                '-P', '-md', 'sha1'], stdout=kfile, shell=False,
                               close_fds=True)

    # Encrypt and store password

    sfd = os.open (bibpath ('secret.bin'),
                   os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                   0o600) # just in case ...

    key, iv = _load_secret_keys ()

    try:
        set_terminal_echo (sys.stdin, False)
        print ('Enter password, then Enter, then control-D twice:')

        with io.open (sfd, 'wb') as sfile:
            subprocess.check_call ([openssl, 'enc', '-aes-256-cbc', '-e', '-K',
                                    key, '-iv', iv], stdout=sfile, shell=False,
                                   close_fds=True)

        print ('Success.')
    finally:
        set_terminal_echo (sys.stdin, True)


def load_user_secret (cfg):
    import subprocess
    openssl = cfg.get_or_die ('apps', 'openssl')

    key, iv = _load_secret_keys ()
    secret = subprocess.check_output ([openssl, 'enc', '-aes-256-cbc', '-d',
                                       '-K', key, '-iv', iv, '-in',
                                       bibpath ('secret.bin')], shell=False,
                                      close_fds=True)
    secret = secret[:-1] # strip trailing newline imposed by our input method
    return secret
