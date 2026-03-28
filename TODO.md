# TODO

## Security
- [x] Replace SHA-256 password hashing with a slow password hashing algorithm such as Argon2id or bcrypt.
- [ ] Prevent cross-user data access by introducing user ownership and authorization checks for comments, enrichment, analysis, and extraction workflows.
- [ ] Remove `pickle`-based cookie deserialization for Instagram session reuse or replace it with a safer storage format and integrity controls.
- [ ] Enforce secure production cookie settings (`JWT_COOKIE_SECURE`, `SameSite`, production-only debug off) and separate local/dev configuration from deployment defaults.
- [ ] Add rate limiting or abuse controls for `/login`, `/process-data`, `/enrich-comments`, and analysis endpoints.
- [ ] Stop returning raw exception messages to clients; return safe generic errors and keep detailed diagnostics only in server logs.
- [ ] Make login responses resistant to username enumeration by using consistent auth failure messages and behavior.
- [ ] Remove hardcoded absolute signup API origin and use same-origin requests consistently.
- [ ] Restrict CORS to explicit trusted origins instead of the current open default.
