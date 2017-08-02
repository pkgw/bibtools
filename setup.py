#! /usr/bin/env python
# Copyright 2014-2017 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License version 3 or higher

# I don't use the ez_setup module because it causes us to automatically build
# and install a new setuptools module, which I'm not interested in doing.

from setuptools import setup

setup (
    name = 'bibtools',
    version = '0.3',

    # This package actually *is* zip-safe, but I've run into issues with
    # installing it as a Zip: in particular, the install sometimes fails with
    # "bad local file header", and backtraces don't include source lines.
    # These are annoying enough and I don't really care so we just install it
    # as flat files.
    zip_safe = False,

    packages = ['bibtools', 'bibtools.hacked_bibtexparser'],

    install_requires = [
        'pwkit >= 0.8.0',
        'six >= 1.10',
    ],

    package_data = {
        'bibtools': ['*.sql', 'apj-issnmap.txt', 'defaults.cfg'],
    },

    entry_points = {
        'console_scripts': ['bib = bibtools.cli:commandline'],
    },

    author = 'Peter Williams',
    author_email = 'peter@newton.cx',
    description = 'Command-line bibliography manager',
    license = 'GPLv3',
    keywords = 'bibliography',
    url = 'https://github.com/pkgw/bibtools/',
)
