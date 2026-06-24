## 2026-06-18 - Open Redirect Evasion using `///` and `/\/\`
**Vulnerability:** Open redirect evasion due to `urllib.parse.urlparse` returning empty netloc for `///example.com`, tricking local path validators. The custom `safe_redirect` utility verified `not parsed.netloc and url.startswith("/")` allowing redirect evasion to arbitrary sites.
**Learning:** `urlparse` doesn't strictly parse all invalid URI formats as one might expect. Paths starting with double slashes `//` are network-path references and can still be used for off-site routing.
**Prevention:** Validate URL redirect limits with `not url.startswith("//")` alongside standard scheme/netloc checks to avoid protocol-relative URI redirects.
