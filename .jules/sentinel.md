## 2026-06-14 - Fail Fast on Weak Default Secrets
**Vulnerability:** The application was not verifying whether a weak default `SECRET_KEY` ('change-me' or '') was present during startup in non-debug mode. If deployed to production without being overridden, all JWTs could be forged.
**Learning:** Security-critical configuration defaults must be actively guarded against in production execution paths, rather than just documented.
**Prevention:** Integrate proactive `validate_production_secrets()` checks within application lifecycle/startup events to ensure weak defaults prevent the application from starting entirely in non-debug environments.
