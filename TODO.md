# TODO

## Security
- [ ] Enforce secure production cookie settings (`JWT_COOKIE_SECURE`, `SameSite`, production-only debug off) and separate local/dev configuration from deployment defaults.
- [ ] Add rate limiting or abuse controls for `/login`, `/process-data`, `/enrich-comments`, and analysis endpoints.
- [ ] Stop returning raw exception messages to clients; return safe generic errors and keep detailed diagnostics only in server logs.
- [ ] Make login responses resistant to username enumeration by using consistent auth failure messages and behavior.
- [ ] Remove hardcoded absolute signup API origin and use same-origin requests consistently.
- [ ] Restrict CORS to explicit trusted origins instead of the current open default.

## Models
- [ ] analyze and find the best current models for sentiment analysis of social media texts
- [ ] find marked datasets for fine-tuning new models
- [ ] find the best way to split comments to different languages 
