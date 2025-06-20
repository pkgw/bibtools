# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2022 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Proxies.
"""

import json
import os
import sys

try:
    from urllib import error, request
except ImportError:
    import urrlib2 as error
    import urrlib2 as request

try:
    from urllib.parse import parse_qs
except ImportError:
    from urlparse import parse_qs

from .util import *
from .webutil import *

__all__ = ("get_proxy").split()


def _init_debug_proxy():
    v = os.environ.get("BIBTOOLS_DEBUG_PROXY", "0")

    try:
        return int(v)
    except ValueError:
        print(
            "warning: unrecognized value %r for $BIBTOOLS_DEBUG_PROXY; should be an integer"
            % v
        )
        return 0


DEBUG_PROXY = _init_debug_proxy()


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


class Redir(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        if "validate.perfdrive.com" in newurl:
            raise Exception("oh no, bot thingie got us")
        return super(Redir, self).redirect_request(req, fp, code, msg, hdrs, newurl)


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
        rh = Redir()  # request.HTTPRedirectHandler()
        rh.max_redirections = 20
        self.opener = request.build_opener(rh, request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [
            ("User-Agent", user_agent),
            (
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            ),
            # ("Accept-Encoding", "gzip, deflate, br"),
            ("Accept-Encoding", "deflate, br"),
            ("Pragma", "no-cache"),
            ("Cache-Control", "no-cache"),
            (
                "sec-ch-ua",
                '" Not A;Brand";v="99", "Chromium";v="96", "Google Chrome";v="96"',
            ),
            ("sec-ch-ua-mobile", "?0"),
            ("sec-ch-ua-platform", '"Linux"'),
            ("Upgrade-Insecure-Requests", "1"),
            ("Sec-Fetch-Site", "none"),
            ("Sec-Fetch-Mode", "navigate"),
            ("Sec-Fetch-User", "?0"),
            ("Sec-Fetch-Dest", "document"),
            ("Accept-Language", "en-US,en;q=0.9"),
        ]
        ###self.opener.process_request['http'][0].set_http_debuglevel(1)
        ###self.opener.process_request['https'][0].set_http_debuglevel(1)

        self.inputs = list(self.default_inputs)
        self.inputs.append(("username", username))
        self.inputs.append(("password", password))

    def do_login(self, resp):
        if DEBUG_PROXY:
            print(f"proxy: starting login flow", file=sys.stderr)

        # XXX we should verify the SSL cert of the counterparty, lest we send
        # our password to malicious people.
        parser = parse_http_html(resp, GenericFormParser())

        if parser.formurl is None:
            posturl = resp.url
        else:
            _scheme, _loc, _path, params, query, frag = urlparse(resp.url)
            posturl = urljoin(resp.url, parser.formurl)
            scheme, loc, path, _params, _query, _frag = urlparse(posturl)
            posturl = urlunparse((scheme, loc, path, params, query, frag))

        values = {}

        for name, value in parser.inputs:
            values[name] = value

        for name, value in self.inputs:
            values[name] = value

        if DEBUG_PROXY:
            print(
                f"proxy: login POST url is `{posturl}`",
                file=sys.stderr,
            )

        req = request.Request(posturl, urlencode(values).encode("utf8"))
        resp = self.opener.open(req)

        if DEBUG_PROXY:
            # In frameless, resp.url is /frame/frameless/v4/auth
            # and we've finished the "Inner Harvard login" step
            print(f"proxy: result is {resp.status}, `{resp.url}`", file=sys.stderr)

        if "duosecurity.com/" in resp.url:
            if DEBUG_PROXY:
                print(
                    "proxy: frameless Duo two-factor seems to be in effect",
                    file=sys.stderr,
                )
            duo_frameless = True
        elif not resp.url.startswith(self.login_url):
            # No two-factor: we should be heading to the target page.
            if DEBUG_PROXY:
                print(f"proxy: no two-factor stage needed, I think", file=sys.stderr)
            self.cj.save()
            return resp
        else:
            # XXX this used to be our auth flow but I'm now using the frameless
            # version, and this is probably broken now.
            if DEBUG_PROXY:
                print(
                    "proxy: Duo iframe two-factor seems to be in effect",
                    file=sys.stderr,
                )
            duo_frameless = False

        curloginurl = resp.url

        # If we're here, two-factor auth seems to be in effect. The precise course
        # of action depends on whether we're using the iframe or frameless style.

        if duo_frameless:
            # url1 is where we got redirected to: /frame/frameless/v4/auth. Parse it.
            url1 = resp.url
            parser = parse_http_html(resp, GenericFormParser())
            postitems = {}

            for name, value in parser.inputs:
                postitems[name] = value

            postitems["screen_resolution_width"] = 1920
            postitems["screen_resolution_height"] = 1200
            postitems["color_depth"] = 24
            postitems["is_cef_browser"] = "false"
            postitems["is_ipad_os"] = "false"
            postitems["is_user_verifying_platform_authenticator_available"] = "false"
            postitems["react_support"] = "true"
            xsrf = postitems["_xsrf"]
            postitems = list(postitems.items())
        else:
            # We need to trigger a Duo request using information slurped from
            # the webpage. First we need to POST to a magic URL looking
            # something like http://api-XYZ.duosecurity.com/frame/web/v1/auth,
            # constructed from the info in the Harvard page ...
            #
            # (The official interaction does a GET of this URL first but we can
            # skip it.)

            parser = parse_http_html(resp, HarvardTwoFactorParser())
            if parser.duo_info is None:
                die("malformed two-factor authentication page response?")

            parent_url = resp.url
            if DEBUG_PROXY:
                print(f"proxy: Duo parent URL is `{parent_url}`", file=sys.stderr)

            tx_signature, app_signature = parser.duo_info["data-sig-request"].split(":")

            query = urlencode(
                [
                    ("parent", parent_url),
                    ("tx", tx_signature),
                    ("v", "2.6"),
                ]
            )

            url1 = urlunparse(
                (
                    "https",
                    parser.duo_info["data-host"],
                    "/frame/web/v1/auth",
                    "",
                    query,
                    "",
                )
            )

            postitems = [
                ("parent", parent_url),
                ("referer", parent_url),
                ("java_version", ""),
                ("flash_version", ""),
                ("screen_resolution_width", "1024"),
                ("screen_resolution_height", "768"),
                ("color_depth", "24"),
                ("is_cef_browser", "false"),
            ]

        # In frameless, we POST back to the URL we just got,
        # `/frame/frameless/v4/auth`. This is initiating Step 4, "Duo login
        # screen"
        postdata = urlencode(postitems)
        if DEBUG_PROXY:
            print(f"proxy: step 4 POST URL is `{url1}`", file=sys.stderr)

        req = request.Request(url1, data=postdata.encode("utf8"))
        resp = self.opener.open(req)

        if DEBUG_PROXY:
            print(
                f"proxy: result is {resp.status}, `{resp.url}`",
                file=sys.stderr,
            )

        if duo_frameless and "key-idp.iam.harvard.edu" in resp.url:
            self.cj.save()
            return resp

        # if "/frame/v4/auth/prompt" not in resp.url:
        #    die("MESSED UP STEP 4")

        if duo_frameless:
            scheme, loc, path, params, query, frag = urlparse(url1)
            data_url = urlunparse(
                (scheme, loc, "/frame/v4/auth/prompt/data", params, query, frag)
            )

            if DEBUG_PROXY:
                print(f"proxy: v4 data URL is `{data_url}`", file=sys.stderr)

            data_req = request.Request(data_url)
            data_resp = self.opener.open(data_req)

            if DEBUG_PROXY:
                print(f"proxy: result is {data_resp.status}", file=sys.stderr)
            data = json.load(data_resp)
            device_key = data["response"]["phones"][0]["key"]
            device_name = data["response"]["phones"][0]["index"]

            url1 = urlunparse((scheme, loc, "/frame/v4/prompt", params, query, frag))
            values = {}
            values["device"] = device_name
            values["factor"] = "Duo Push"
            sid = parse_qs(query)["sid"][0]
            values["sid"] = sid
        else:
            parser = parse_http_html(resp, GenericFormParser())
            values = {}

            for name, value in parser.inputs:
                values[name] = value

            values["factor"] = "Duo Push"  # force this method!

        # frameless: This is the post to /frame/v4/prompt This request is Step
        # 6, and it causes the notification to actually get pushed in the
        # frameless flow.

        if DEBUG_PROXY:
            print(
                f"proxy: prompt POST url is `{url1}`",
                file=sys.stderr,
            )

        headers = {
            "X-Xsrftoken": xsrf,
        }
        postdata = urlencode(list(values.items()))
        req = request.Request(url1, data=postdata.encode("utf8"), headers=headers)
        resp = self.opener.open(req)

        if DEBUG_PROXY:
            print(
                f"proxy: result is {resp.status}, `{resp.url}`",
                file=sys.stderr,
            )

        try:
            data = json.load(resp)
            assert data["stat"] == "OK", "unexpected Duo response: " + repr(data)
            txid = data["response"]["txid"]
        except Exception as e:
            die(f"failed to parse Duo push response: {e} ({e.__class__.__name__})")

        url3 = urlunparse((scheme, loc, "/frame/v4/status", "", "", ""))

        if DEBUG_PROXY:
            print(
                f"proxy: status POST url is `{url3}`",
                file=sys.stderr,
            )

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
            print("[Success! Continuing ...]")
        else:
            die("Duo two-factor approval never came through?")

        if "cookie" in data["response"]:
            # Oldest behavior
            cookie = data["response"].get("cookie")
        elif data["response"].get("post_auth_action") == "oidc_exit":
            # Dec 2021: POST to OIDC exit API
            url4 = urlunparse((scheme, loc, "/frame/v4/oidc/exit", "", "", ""))

            if DEBUG_PROXY:
                print(
                    f"proxy: OIDC exit POST url is `{url4}`",
                    file=sys.stderr,
                )

            postdata = urlencode(
                [
                    ("dampen_choice", "true"),
                    ("sid", sid),
                    ("txid", txid),
                    ("factor", "Duo Push"),
                    ("device_key", device_key),
                    ("_xsrf", xsrf),
                ]
            )
            req = request.Request(url4, postdata.encode("utf8"))
            self.cj.save()
            return self.opener.open(req)
        else:
            # Sep 2018: another URL to post to
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
        if DEBUG_PROXY:
            print(f"proxy: starting postback flow", file=sys.stderr)

        parser = parse_http_html(resp, GenericFormParser())
        posturl = urljoin(resp.url, parser.formurl)

        if DEBUG_PROXY:
            print(f"proxy: postback URL is `{posturl}`", file=sys.stderr)

        values = {}

        for name, value in parser.inputs:
            values[name] = value

        req = request.Request(posturl, urlencode(values).encode("utf8"))
        resp = self.opener.open(req)

        if DEBUG_PROXY:
            print(f"proxy: result is {resp.status}, `{resp.url}`", file=sys.stderr)

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

            req = request.Request(
                posturl, urlencode(values).encode("utf8"), headers={"Referer": posturl}
            )
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

        if DEBUG_PROXY:
            print(f"proxy: fetching proxied URL `{proxyurl}`", file=sys.stderr)

        try:
            resp = self.opener.open(proxyurl)
        except error.HTTPError as e:
            if e.code == 404:
                # The proxy doesn't feel like proxying this URL. Try just
                # accessing it directly.
                if DEBUG_PROXY:
                    print(
                        f"proxy: 404; falling back to original `{url}`", file=sys.stderr
                    )
                return self.opener.open(url)
            raise e

        if DEBUG_PROXY:
            print(f"proxy: result is {resp.status}, `{resp.url}`", file=sys.stderr)

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
