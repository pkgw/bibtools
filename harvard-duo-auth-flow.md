# Harvard Two-Factor Authentication Flow with Duo Mobile.

Here are some notes on the fun HTTP transaction that has to occur to
authenticate for the Harvard Library proxy using two-factor authentication
with Duo Mobile. PKGW has private notes with more details (just in case those
details leak anything important).

Make sure to honor cookies.

1. GET the proxied URL (`iopscience-iop-org...`) and follow redirects until you ...
2. GET `www.pin1.harvard.edu/cas/login`.
3. Emit a new request: POST `www.pin1.harvard.edu/cas/login`
  - POST URL is same as we just GET-ed.
  - Form data username and password are our secrets
  - Other form data come from the HTML (thankfully, including the scary `execution` datum)
  - Update a cookie (AWSALB)
  - Result is code 200.
4. Emit a new request: GET `api-7052d448.duosecurity.com/frame/web/v1/auth`
  - Domain name and query string param `tx` come from the HTML `<iframe>` defining the Duo interface
  - Query string param `parent` is the just `cas/login` URL.
  - Looks like you can skip this and go straight to the POST.
5. Emit a new request: POST `api-7052d448.duosecurity.com/frame/web/v1/auth`
  - POST URL is the same as we just GET-ed.
  - Form data `parent` = `referer` = the `cas/login` URL.
  - Rest of form data is trivial
6. Follow the 302 response: GET `api-7052d448.duosecurity.com/frame/prompt`
  - Result is code 200.
7. Emit a new request: POST `api-7052d448.duosecurity.com/frame/prompt`
  - Form data `sid` is the query string `sid` of the previous request
  - Rest of form data is trivial
8. Emit an XMLHttpRequest: POST `api-7052d448.duosecurity.com/frame/status`
  - Form data `sid` is the same.
  - Form data `txid` comes from the Duo response data
  - Response is code 200, presumably small JSON
9. Emit the same POST request
  - Won't return until user has given two-factor approval
10. Emit an XMLHttpRequest: POST `api-7052d448.duosecurity.com/frame/status/64550ef2-ba37-42e9-b441-5ff5c618ab8d`
  - URL comes from `result_url` of the Duo response
  - Response is code 200, presumably small JSON
11. Emit a new request: POST `www.pin1.harvard.edu/cas/login`
  - URL is the same as previous `cas/login` events
  - Form data `signedDuoResponse` is synthesized from Duo's `cookie`
  - Rest of form data is trivial
12. Follow 302 responses until you get back to your URL!
