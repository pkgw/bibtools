# -*- mode: python; coding: utf-8 -*-
# Copyright 2014-2016 Peter Williams <peter@newton.cx>
# Licensed under the GNU General Public License, version 3 or higher.

"""
Proxies.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

try:
    from http import cookiejar
except ImportError:
    import cookielib as cookiejar

try:
    from urllib import error, request
except ImportError:
    import urrlib2 as error
    import urrlib2 as request


from .util import *
from .webutil import *

__all__ = ('get_proxy').split ()


class HarvardProxyLoginParser (HTMLParser):
    def __init__ (self):
        HTMLParser.__init__ (self)
        self.formurl = None
        self.inputs = []


    def handle_starttag (self, tag, attrs):
        if tag == 'form':
            attrs = dict (attrs)
            self.formurl = attrs.get ('action')
            if attrs.get ('method') != 'post':
                die ('unexpected form method')
        elif tag == 'input':
            attrs = dict (attrs)
            if 'name' not in attrs or 'value' not in attrs:
                die ('missing form input information')
            self.inputs.append ((attrs['name'], attrs['value']))


class HarvardTwoFactorParser (HarvardProxyLoginParser):
    def __init__ (self):
        HarvardProxyLoginParser.__init__ (self)
        self.duo_info = None
        self.in_script = False


    def handle_starttag (self, tag, attrs):
        if tag == 'script':
            self.in_script = True
        return HarvardProxyLoginParser.handle_starttag (self, tag, attrs)


    def handle_endtag (self, tag):
        if tag == 'script':
            self.in_script = False


    def handle_data (self, data):
        if not self.in_script:
            return

        if 'Duo.init' not in data:
            return

        import json
        try:
            i0 = data.index ('{')
            i1 = data.rindex ('}')
            span = data[i0:i1+1]
            filtered = span.replace ("'", '"') # Python needs this
            self.duo_info = json.loads (filtered)
        except Exception as e:
            pass


class HarvardProxy (object):
    suffix = '.ezp-prod1.hul.harvard.edu'
    loginurl = 'https://www.pin1.harvard.edu/cas/login'
    forwardurl = 'http://ezp-prod1.hul.harvard.edu/connect'

    default_inputs = [
        ('authenticationSourceType', 'HarvardKey'),
    ]

    def __init__ (self, user_agent, username, password):
        self.cj = cookiejar.CookieJar ()

        # Older articles in Wiley's Online Library hit the default limit of 10
        # redirections.
        rh = request.HTTPRedirectHandler ()
        rh.max_redirections = 20
        self.opener = request.build_opener (rh, request.HTTPCookieProcessor (self.cj))
        self.opener.addheaders = [('User-Agent', user_agent)]
        ###self.opener.process_request['http'][0].set_http_debuglevel (1)
        ###self.opener.process_request['https'][0].set_http_debuglevel (1)

        self.inputs = list (self.default_inputs)
        self.inputs.append (('username', username))
        self.inputs.append (('password', password))


    def login (self, resp):
        # XXX we should verify the SSL cert of the counterparty, lest we send
        # our password to malicious people.
        parser = parse_http_html (resp, HarvardProxyLoginParser ())

        if parser.formurl is None:
            die ('malformed proxy page response?')

        posturl = urljoin (resp.url, parser.formurl)
        values = {}

        for name, value in parser.inputs:
            values[name] = value

        for name, value in self.inputs:
            values[name] = value

        req = request.Request (posturl, urlencode (values).encode('utf8'))
        resp = self.opener.open (req)

        if not resp.url.startswith (self.loginurl):
            # No two-factor: we should be heading to the target page.
            return resp

        curloginurl = resp.url

        # If we're here, two-factor auth seems to be in effect. We need to
        # trigger a Duo request using information slurped from the webpage.
        # First we need to POST to a magic URL looking something like
        # http://api-XYZ.duosecurity.com/frame/web/v1/auth, constructed from
        # the info in the Harvard page ...

        parser = parse_http_html (resp, HarvardTwoFactorParser ())
        if parser.duo_info is None:
            die ('malformed two-factor authentication page response?')

        tx_signature, app_signature = parser.duo_info['sig_request'].split (':')

        query = urlencode ([
            ('parent', resp.url),
            ('tx', tx_signature),
        ])

        url1 = urlunparse (('https', parser.duo_info['host'],
                            '/frame/web/v1/auth', '', query, ''))

        postdata = urlencode ([
            ('parent', resp.url),
        ])
        req = request.Request (url1, postdata.encode('utf8'))
        resp = self.opener.open (req)

        # Now we get redirected to
        # http://api-XYZ.duosecurity.com/frame/prompt/new. We then need to
        # issue a POST to the same path. The response is JSON containing
        # a transaction ID.

        scheme, loc, path, params, query, frag = urlparse (resp.url)
        try:
            from urllib.parse import parse_qs
        except ImportError:
            from urlparse import parse_qs
        sid = parse_qs (query)['sid'][0]

        url2 = urlunparse ((scheme, loc, path, '', '', ''))
        postdata = urlencode ([
            ('sid', sid),
            ('device', 'phone1'), # XXX: does this vary?
            ('factor', 'Duo Push'),
            ('out_of_date', 'False'),
        ])
        req = request.Request (url2, postdata.encode('utf8'))
        resp = self.opener.open (req)

        import json

        try:
            data = json.load (resp)
            assert data['stat'] == 'OK', 'unexpected Duo response: ' + repr (data)
            txid = data['response']['txid']
        except Exception as e:
            die ('failed to parse Duo push response: %s', e)

        # Now we can issue another POST to /frame/status, which finally
        # actually pushes the notification.

        url3 = urlunparse ((scheme, loc, '/frame/status', '', '', ''))
        postdata = urlencode ([
            ('sid', sid),
            ('txid', txid),
        ])
        req = request.Request (url3, postdata.encode('utf8'))
        resp = self.opener.open (req)

        try:
            data = json.load (resp)
            assert data['stat'] == 'OK', 'unexpected Duo response: ' + repr (data)
        except Exception as e:
            die ('failed to parse Duo push response: %s', e)

        # Now we POST again. This time the response doesn't finish until the
        # human has approved or denied the request.

        print ('[Waiting for two-factor approval ...]')
        req = request.Request (url3, postdata.encode('utf8'))
        resp = self.opener.open (req)

        try:
            data = json.load (resp)
            assert data['stat'] == 'OK', 'unexpected Duo response: ' + repr (data)
        except Exception as e:
            die ('failed to parse Duo push response: %s', e)

        if data['response'].get ('status_code', 'undef') == 'allow':
            cookie = data['response']['cookie']
            print ('[Success! Continuing ...]')
        else:
            die ('Duo two-factor approval never came through?')

        # Finally we can go back to the Harvard login page and submit our
        # authentication. Note that the list of inputs that we have to send
        # back is not identical to the ones that we got from the very first
        # page request (the "LT" variable changes).

        postdata = urlencode (parser.inputs + [
            ('signedDuoResponse', cookie + ':' + app_signature),
        ])
        req = request.Request (curloginurl, postdata.encode('utf8'))
        return self.opener.open (req)


    def open (self, url):
        scheme, loc, path, params, query, frag = urlparse (url)

        if scheme == 'https':
            # Because of how wildcard SSL certificates work, if we're trying
            # to proxy an HTTPS URL, the dots in the target domain get
            # replaced with dashes.
            proxydomain = loc.replace ('.', '-') + self.suffix
        else:
            proxydomain = loc + self.suffix

        proxyurl = urlunparse ((scheme, proxydomain, path,
                                params, query, frag))

        try:
            resp = self.opener.open (proxyurl)
        except error.HTTPError as e:
            if e.code == 404:
                # The proxy doesn't feel like proxying this URL. Try just
                # accessing it directly.
                return self.opener.open (url)
            raise e

        if resp.url.startswith (self.loginurl):
            resp = self.login (resp)

        if resp.url.startswith (self.forwardurl):
            # Sometimes we get forwarded to a separate cookie-setting page
            # that requires us to re-request the original URL.
            resp = self.opener.open (proxyurl)

        return resp


    def unmangle (self, url):
        if url is None:
            return None # convenience

        scheme, loc, path, params, query, frag = urlparse (url)
        if not loc.endswith (self.suffix):
            return url

        loc = loc[:-len (self.suffix)]

        if scheme == 'https':
            # We'll break for domains with hyphens in them, but there's
            # no avoiding that as far as I can tell. This is probably the
            # more robust way to go.
            loc = loc.replace ('-', '.')

        return urlunparse ((scheme, loc, path, params, query, frag))


class NullProxy (object):
    def __init__ (self, user_agent):
        pass # XXX we should honor user_agent; see below.

    def open (self, url):
        return urlopen (url)

    def unmangle (self, url):
        return url


def get_proxy (cfg):
    from .secret import load_user_secret
    from .config import Error

    try:
        kind = cfg.get ('proxy', 'kind')
        username = cfg.get ('proxy', 'username')
    except Error:
        kind = None

    # This is awkward. All proxies have to be able to send a User-Agent that
    # we specify. This is because otherwise nature.com gives us its mobile
    # site, which happens to not include the easily-recognized <a> tag linking
    # to the paper PDF. I don't know exactly what's needed, but if we just
    # send 'Mozilla/5.0' as the UA, nature.com gives us a 500 error (!). So
    # I've just copied my current browser's UA.
    ua = cfg.get_or_die ('proxy', 'user-agent')

    # It's not good to have the password hanging around in memory, but Python
    # strings are immutable and we have no idea what (if anything) `del
    # password` would accomplish, so I don't think we can really do better.

    if kind == 'harvard':
        password = load_user_secret (cfg)
        return HarvardProxy (ua, username, password)

    warn ('no proxy defined; will likely have trouble obtaining full-text articles')
    return NullProxy (ua)
