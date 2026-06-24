## 2024-06-14 - Weak Default Secret Key Startup Guard
**Vulnerability:** The application was initialized with a default `secret_key` of 'change-me' and no runtime enforcement to prevent its use in production. An attacker who knows this default could forge valid JWT tokens for any role.
**Learning:** Default secrets provided for developer convenience can easily slip into production if not explicitly guarded against at startup.
**Prevention:** Implemented a fail-fast startup guard in `lifespan` that checks if the application is running with `debug=False` and a known weak `secret_key`, raising a `RuntimeError` to prevent startup until a secure key is configured.
