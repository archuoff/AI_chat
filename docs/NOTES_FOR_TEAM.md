# Notes and questions for the Chromosome team (frontend)

## How the remote is built
* Angular 20, standalone components, zoneless, signals, SCSS (component styles, nothing global), no SSR, no NgModules.
* Exposes `./Routes` (`src/app/app.routes.ts`); the routes are `chat`, `manage`, `users` under one shell with a slim tab bar.
* No authentication logic and no global state: role and allowed domains are read from the backend (`GET .../me`); the pages only hide what the backend would refuse anyway.
* **Only `HttpClient` is used** (calls, file upload, the chat stream via progress events, picture files as blobs). The host's interceptor therefore adds the token to everything.
* Styles are scoped: shared classes are prefixed `eng-` and live under `.eng-root`; the remote does not touch the host's global CSS.
* Two small libraries were added (need your approval): `marked` (markdown in answers, with GFM tables) and `dompurify` (sanitising the generated HTML).

## Questions
1. **Token.** Does the host interceptor attach `access-token` to requests whose URL starts with a configured API address? What is the pattern for a new service?
2. **Backend address.** `engismartUrl` assumes `<origin>/<base>/engismart/api/v1` (gateway path); the remote adds `/engismart_chat` (chat, picture files) and `/engismart_ingestion` (library, users) itself. Please confirm per environment.
3. **Remote path / name.** The template's `angular.json` has `baseHref`/`deployUrl` `/mf1/ml-accelerator/`. Which path does Engismart get, and what remote name does the host use?
4. **Shared libraries.** `federation.config.js` shares everything as singleton with `strictVersion`. Do the host's Angular versions match (^20.1)?
5. **Layout.** The remote has its own tab bar and needs a body of at least ~560 px height. Is there a host layout we should fit into (page title, breadcrumbs)?
6. **Theme.** Colours are fixed variables on `.eng-root` (`--eng-primary`, ...). If the host publishes theme variables, we can map to them.
7. Unit tests (Karma) were not added to this delivery; the template's `app.spec.ts` is unchanged.

## Verified here
Built with Angular 20.3 and Node 22; run in Chromium against the real backend (platform login by token): chat with streaming and sources, library, document detail,
sheet preview with 13 pictures in their cells, pictures tab, upload with "likely update" suggestion and replace, users and domain limits, a normal user bounced
from Manage to Chat, and a user without the application seeing a clear message.
