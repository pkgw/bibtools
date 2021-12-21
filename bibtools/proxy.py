# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2021 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Proxies.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

try:
    from urllib import error, request
except ImportError:
    import urrlib2 as error
    import urrlib2 as request


from .util import *
from .webutil import *

__all__ = ('get_proxy').split()


class GenericFormParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.formurl = None
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        if tag == "form":
            attrs = dict(attrs)

            # on the EZProxy postback page, there's a secondary form that's
            # not what we want.
            if attrs.get("method", "undef").lower() != "post":
                return

            self.formurl = attrs.get("action")
        elif tag == "input":
            attrs = dict(attrs)
            if attrs.get("type", "other") == "submit":
                return
            if "name" not in attrs:
                die("missing form input information")
            self.inputs.append((attrs["name"], attrs.get("value", "")))


class HarvardTwoFactorParser(GenericFormParser):
    def __init__(self):
        GenericFormParser.__init__(self)
        self.duo_info = None

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            attrs_dict = dict(attrs)
            if attrs_dict.get("id") == "duo_iframe":
                self.duo_info = attrs_dict

        return GenericFormParser.handle_starttag(self, tag, attrs)


class HarvardProxy(object):
    suffix = ".ezp-prod1.hul.harvard.edu"
    login_url = "https://www.pin1.harvard.edu/cas/login"
    forward_url = "http://ezp-prod1.hul.harvard.edu/connect"
    postback1_url = "https://login.ezp-prod1.hul.harvard.edu/login"
    postback2_url = "https://key-idp.iam.harvard.edu/idp/"

    default_inputs = [
        ("authenticationSourceType", "HarvardKey"),
        ("source", "HARVARDKEY"),
    ]

    def __init__(self, user_agent, username, password):
        self.cj = get_persistent_cookiejar()

        # Older articles in Wiley's Online Library hit the default limit of 10
        # redirections.
        rh = request.HTTPRedirectHandler()
        rh.max_redirections = 20
        self.opener = request.build_opener(rh, request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [("User-Agent", user_agent)]
        ###self.opener.process_request['http'][0].set_http_debuglevel(1)
        ###self.opener.process_request['https'][0].set_http_debuglevel(1)

        self.inputs = list(self.default_inputs)
        self.inputs.append(("username", username))
        self.inputs.append(("password", password))

    def do_login(self, resp):
        # XXX we should verify the SSL cert of the counterparty, lest we send
        # our password to malicious people.
        parser = parse_http_html(resp, GenericFormParser())

        if parser.formurl is None:
            posturl = resp.url
        else:
            posturl = urljoin(resp.url, parser.formurl)

        values = {}

        for name, value in parser.inputs:
            values[name] = value

        for name, value in self.inputs:
            values[name] = value

        req = request.Request(posturl, urlencode(values).encode("utf8"))
        resp = self.opener.open(req)

        if not resp.url.startswith(self.login_url):
            # No two-factor: we should be heading to the target page.
            self.cj.save()
            return resp

        curloginurl = resp.url

        # If we're here, two-factor auth seems to be in effect. We need to
        # trigger a Duo request using information slurped from the webpage.
        # First we need to POST to a magic URL looking something like
        # http://api-XYZ.duosecurity.com/frame/web/v1/auth, constructed from
        # the info in the Harvard page ...
        #
        # (The official interaction does a GET of this URL first but we can
        # skip it.)

        parser = parse_http_html(resp, HarvardTwoFactorParser())
        if parser.duo_info is None:
            die("malformed two-factor authentication page response?")

        parent_url = resp.url
        tx_signature, app_signature = parser.duo_info["data-sig-request"].split(":")

        query = urlencode(
            [
                ("parent", parent_url),
                ("tx", tx_signature),
                ("v", "2.6"),
            ]
        )

        url1 = urlunparse(
            ("https", parser.duo_info["data-host"], "/frame/web/v1/auth", "", query, "")
        )

        postdata = urlencode(
            [
                ("parent", parent_url),
                ("referer", parent_url),
                ("java_version", ""),
                ("flash_version", ""),
                ("screen_resolution_width", "1024"),
                ("screen_resolution_height", "768"),
                ("color_depth", "24"),
                ("is_cef_browser", "false"),
            ]
        )
        req = request.Request(url1, postdata.encode("utf8"))
        resp = self.opener.open(req)

        # Now we get redirected to
        # http://api-XYZ.duosecurity.com/frame/prompt. We then need to issue a
        # POST to the same path. The response is JSON containing a transaction
        # ID.

        scheme, loc, path, params, query, frag = urlparse(resp.url)
        try:
            from urllib.parse import parse_qs
        except ImportError:
            from urlparse import parse_qs
        sid = parse_qs(query)["sid"][0]

        url2 = urlunparse((scheme, loc, path, "", "", ""))
        postdata = urlencode(
            [
                ("sid", sid),
                ("device", "phone1"),  # XXX: does this vary?
                ("factor", "Duo Push"),
                ("out_of_date", ""),
                ("days_out_of_date", ""),
                ("days_to_block", "None"),
            ]
        )
        req = request.Request(url2, postdata.encode("utf8"))
        resp = self.opener.open(req)

        import json

        try:
            data = json.load(resp)
            assert data["stat"] == "OK", "unexpected Duo response: " + repr(data)
            txid = data["response"]["txid"]
        except Exception as e:
            die("failed to parse Duo push response: %s", e)

        # Now we can issue another POST to /frame/status, which finally
        # actually pushes the notification.

        url3 = urlunparse((scheme, loc, "/frame/status", "", "", ""))
        postdata = urlencode(
            [
                ("sid", sid),
                ("txid", txid),
            ]
        )
        req = request.Request(url3, postdata.encode("utf8"))
        resp = self.opener.open(req)

        try:
            data = json.load(resp)
            assert data["stat"] == "OK", "unexpected Duo response: " + repr(data)
        except Exception as e:
            die("failed to parse Duo push response: %s", e)

        # Now we POST again. This time the response doesn't finish until the
        # human has approved or denied the request.

        print("[Waiting for two-factor approval ...]")
        req = request.Request(url3, postdata.encode("utf8"))
        resp = self.opener.open(req)

        try:
            data = json.load(resp)
            assert data["stat"] == "OK", "unexpected Duo response: " + repr(data)
        except Exception as e:
            die("failed to parse Duo push response: %s", e)

        if data["response"].get("status_code", "undef") == "allow":
            cookie = data["response"].get("cookie")
            print("[Success! Continuing ...]")
        else:
            die("Duo two-factor approval never came through?")

        # Duo used to work where we got the cookie above. At the moment (Sep
        # 2018) it instead gives us yet another URL that we need to POST to.

        if cookie is None:
            newbase = data["response"]["result_url"]
            url4 = urlunparse((scheme, loc, newbase, "", "", ""))
            req = request.Request(url4, postdata.encode("utf8"))
            resp = self.opener.open(req)

            try:
                data = json.load(resp)
                assert data["stat"] == "OK", "unexpected Duo response: " + repr(data)
            except Exception as e:
                die("failed to parse Duo push response: %s", e)

            cookie = data["response"]["cookie"]

        # Finally we can go back to the Harvard login page and submit our
        # authentication. Note that the list of inputs that we have to send
        # back is not identical to the ones that we got from the very first
        # page request (the "LT" variable changes).

        postdata = urlencode(
            parser.inputs
            + [
                ("signedDuoResponse", cookie + ":" + app_signature),
            ]
        )
        req = request.Request(curloginurl, postdata.encode("utf8"))
        self.cj.save()
        return self.opener.open(req)

    def do_postback(self, resp):
        """When forwarded here, we're given a special HTML page that triggers a POST
        request that we need to work through.

        """
        parser = parse_http_html(resp, GenericFormParser())
        posturl = urljoin(resp.url, parser.formurl)

        values = {}

        for name, value in parser.inputs:
            values[name] = value

        req = request.Request(posturl, urlencode(values).encode("utf8"))
        resp = self.opener.open(req)

        # I'm not sure about all of the possibilities here, but the following
        # logic is my best guess about the different auth flows here.

        if resp.url.startswith(self.login_url):
            # We have to do the login, and then continue with the postback process
            resp = self.do_login(resp)

        if resp.url.startswith(self.postback2_url):
            parser = parse_http_html(resp, GenericFormParser())
            posturl = urljoin(resp.url, parser.formurl)
            values = {}

            for name, value in parser.inputs:
                values[name] = value

            req = request.Request(posturl, urlencode(values).encode("utf8"))
            resp = self.opener.open(req)

        self.cj.save()
        return resp

    def open(self, url):
        scheme, loc, path, params, query, frag = urlparse(url)

        if scheme == "https":
            # Because of how wildcard SSL certificates work, if we're trying
            # to proxy an HTTPS URL, the dots in the target domain get
            # replaced with dashes.
            proxydomain = loc.replace(".", "-") + self.suffix
        else:
            proxydomain = loc + self.suffix

        proxyurl = urlunparse((scheme, proxydomain, path, params, query, frag))

        try:
            resp = self.opener.open(proxyurl)
        except error.HTTPError as e:
            if e.code == 404:
                # The proxy doesn't feel like proxying this URL. Try just
                # accessing it directly.
                return self.opener.open(url)
            raise e

        if resp.url.startswith(self.login_url):
            resp = self.do_login(resp)

        if resp.url.startswith(self.postback1_url):
            resp = self.do_postback(resp)

        if resp.url.startswith(self.forward_url):
            # Sometimes we get forwarded to a separate cookie-setting page
            # that requires us to re-request the original URL.
            resp = self.opener.open(proxyurl)

        self.cj.save()
        return resp

    def unmangle(self, url):
        if url is None:
            return None  # convenience

        scheme, loc, path, params, query, frag = urlparse(url)
        if not loc.endswith(self.suffix):
            return url

        loc = loc[: -len(self.suffix)]

        if scheme == "https":
            # We'll break for domains with hyphens in them, but there's
            # no avoiding that as far as I can tell. This is probably the
            # more robust way to go.
            loc = loc.replace("-", ".")

        return urlunparse((scheme, loc, path, params, query, frag))


class NullProxy(object):
    def __init__(self, user_agent):
        pass  # XXX we should honor user_agent; see below.

    def open(self, url):
        return urlopen(url)

    def unmangle(self, url):
        return url


def get_proxy(cfg):
    from .secret import load_user_secret
    from .config import Error

    try:
        kind = cfg.get("proxy", "kind")
        username = cfg.get("proxy", "username")
    except Error:
        kind = None

    # This is awkward. All proxies have to be able to send a User-Agent that
    # we specify. This is because otherwise nature.com gives us its mobile
    # site, which happens to not include the easily-recognized <a> tag linking
    # to the paper PDF. I don't know exactly what's needed, but if we just
    # send 'Mozilla/5.0' as the UA, nature.com gives us a 500 error (!). So
    # I've just copied my current browser's UA.
    ua = cfg.get_or_die("proxy", "user-agent")

    # It's not good to have the password hanging around in memory, but Python
    # strings are immutable and we have no idea what (if anything) `del
    # password` would accomplish, so I don't think we can really do better.

    if kind == "harvard":
        password = load_user_secret(cfg)
        return HarvardProxy(ua, username, password)

    warn("no proxy defined; will likely have trouble obtaining full-text articles")
    return NullProxy(ua)
