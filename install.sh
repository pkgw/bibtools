#! /bin/bash
# Copyright 2014 Peter Williams
# Licensed under the GNU General Public License version 3 or higher

# Installation is configured with a shell script fragment called 'config.sh'.
# It just needs to set the variable "prefix"
# See the file 'config.sh.sample'.

if [ ! -f config.sh ] ; then
    echo >&2 "Create a file called 'config.sh' to install."
    echo >&2 "(See 'config.sh.sample' for a template.)"
    exit 1
fi

source ./config.sh

if [ x"$prefix" = x ] ; then
    echo >&2 "error: no install prefix configured"
    exit 1
fi

if [ ! -d $prefix/lib/python/site-packages ] ; then
    echo >&2 "error: the directory $prefix/lib/python/site-packages must exist"
    echo >&2 "       to install. Symlink 'pythonX.Y' to 'python' and potentially"
    echo >&2 "       'lib64' to 'lib'."
    exit 1
fi

if [ x"$1" = x-v ] ; then
    vee=v
    echo=echo
else
    vee=
    echo=:
fi


# Done with setup.

mkdir -p$vee $prefix/bin $prefix/share/bib
install -C$vee -m755 -t $prefix/bin bib
install -C$vee -m644 -t $prefix/share/bib *.sql
