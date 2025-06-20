# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2019 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Tools relating to working with NASA's ADS.
"""

import json

from .util import *
from . import webutil as wu
from .bibcore import *

__all__ = "autolearn_bibcode search_ads".split()


def _translate_ads_name(name):
    pieces = [x.strip() for x in name.split(",", 1)]
    surname = pieces[0].replace(" ", "_")
    # TODO use bibcore

    if len(pieces) > 1:
        return pieces[1] + " " + surname
    return surname


def _autolearn_bibcode_tag(info, tag, text):
    # TODO: editors?

    if tag == "T":
        info["title"] = text
    elif tag == "D":
        info["year"] = int(text.split("/")[-1])
    elif tag == "B":
        info["abstract"] = text
    elif tag == "A":
        info["authors"] = [_translate_ads_name(n) for n in text.split(";")]
    elif tag == "Y":
        subdata = dict(s.strip().split(": ", 1) for s in text.split(";"))

        if "DOI" in subdata:
            info["doi"] = subdata["DOI"]
        if "eprintid" in subdata:
            value = subdata["eprintid"]
            if value.startswith("arXiv:"):
                info["arxiv"] = value[6:]


def autolearn_bibcode(app, bibcode):
    """Use the ADS export API to learn metadata given a bibcode.

    We could maybe use a nicer API, but the existing code used the ADS tagged
    format, so we stuck with it in the transition to the non-classic API.

    """
    apikey = app.cfg.get_or_die("api-keys", "ads")

    url = "https://api.adsabs.harvard.edu/v1/export/ads"
    opener = wu.build_opener()
    opener.addheaders = [
        ("Authorization", "Bearer:" + apikey),
        ("Content-Type", "application/json"),
    ]
    post_data = {
        "bibcode": [bibcode],
    }
    raw_content = opener.open(url, data=json.dumps(post_data).encode("utf8"))
    payload = json.load(raw_content)

    info = {"bibcode": bibcode, "keep": 0}  # because we're autolearning
    curtag = curtext = None

    print("[Parsing", url, "...]")

    for line in payload["export"].splitlines():
        line = line.strip()

        if not len(line):
            if curtag is not None:
                _autolearn_bibcode_tag(info, curtag, curtext)
                curtag = curtext = None
            continue

        if curtag is None:
            if line[0] == "%":
                # starting a new tag
                curtag = line[1]
                curtext = line[3:]
            elif line.startswith("Retrieved "):
                if not line.endswith("selected: 1."):
                    die("matched more than one publication")
        else:
            if line[0] == "%":
                # starting a new tag, while we had one going before.
                # finish up the previous
                _autolearn_bibcode_tag(info, curtag, curtext)
                curtag = line[1]
                curtext = line[3:]
            else:
                curtext += " " + line

    if curtag is not None:
        _autolearn_bibcode_tag(info, curtag, curtext)

    return info


# Searching


def _run_ads_search(app, searchterms, filterterms, nrows=50):
    # TODO: access to more API args
    apikey = app.cfg.get_or_die("api-keys", "ads")

    q = [("q", " ".join(searchterms))]

    for ft in filterterms:
        q.append(("fq", ft))

    q.append(("fl", "author,bibcode,title"))  # fields list
    q.append(("rows", nrows))

    url = "http://api.adsabs.harvard.edu/v1/search/query?" + wu.urlencode(q)

    opener = wu.build_opener()
    opener.addheaders = [("Authorization", "Bearer:" + apikey)]
    return json.load(opener.open(url))


def search_ads(app, terms, raw=False, large=False):
    if len(terms) < 2:
        die("require at least two search terms for ADS")

    adsterms = []
    astro_specific = True  # default to this for this service

    for info in terms:
        if info[0] == "year":
            adsterms.append("year:%d" % info[1])
        elif info[0] == "surname":
            adsterms.append('author:"%s"' % info[1])
        elif info[0] == "refereed":
            if info[1]:
                adsterms.append("property:refereed")
            else:
                adsterms.append("property:notrefereed")
        elif info[0] == "astro_specific":
            astro_specific = info[1]
        else:
            die("don't know how to express search term %r to ADS", info)

    if astro_specific:
        filter_terms = ["database:astronomy"]
    else:
        filter_terms = []

    if large:
        nrows = 1000
    else:
        nrows = 50

    try:
        r = _run_ads_search(
            app, adsterms, filter_terms, nrows=nrows
        )  # XXX more hardcoding
    except Exception as e:
        die("could not perform ADS search: %s", e)

    if raw:
        import sys

        json.dump(r, sys.stdout, ensure_ascii=False, indent=2, separators=(",", ": "))
        return

    query_row_limit = r.get("responseHeader", {}).get("params", {}).get("rows")
    if query_row_limit is not None:
        query_row_limit = int(query_row_limit)
    else:
        # default specified by ADS API docs:
        # https://github.com/adsabs/adsabs-dev-api/blob/master/search.md
        query_row_limit = 10

    maxbclen = 0
    info = []
    if large:
        ntrunc = 2147483647  # 2**31-1, probably big enough
    else:
        ntrunc = 20
    nresults = len(r["response"]["docs"])

    for item in r["response"]["docs"][:ntrunc]:
        # year isn't important since it's embedded in bibcode.
        if "title" in item:
            title = item["title"][0]  # not sure why this is a list?
        else:
            title = "(no title)"  # this happens, e.g.: 1991PhDT.......161G
        bibcode = item["bibcode"]
        authors = ", ".join(
            parse_name(_translate_ads_name(n))[1] for n in item["author"]
        )

        maxbclen = max(maxbclen, len(bibcode))
        info.append((bibcode, title, authors))

    ofs = maxbclen + 2
    red, reset = get_color_codes(None, "red", "reset")

    for bc, title, authors in info:
        print("%s%*s%s  " % (red, maxbclen, bc, reset), end="")
        print_truncated(title, ofs, color="bold")
        print("    ", end="")
        print_truncated(authors, 4)

    if nresults >= ntrunc:
        print("")
        if nresults < query_row_limit:
            print("(showing %d of %d results)" % (ntrunc, nresults))
        else:
            print("(showing %d of at least %d results)" % (ntrunc, query_row_limit))
