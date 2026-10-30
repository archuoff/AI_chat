# What to do on your side (frontend)

Node 20.19+ / 22 (same as your other Angular 20 remotes) and npm are enough. The tool uses only Node's standard library.

## A. Let the tool add Engismart to your GitLab clone (recommended)
1. Get this branch onto the office PC (zip from your phone / Teams).
2. In the folder that holds `tools/` run, with the path of your clone of the remote repo (the folder that has `federation.config.js`):
   ```
   node tools\assemble.mjs --template C:\path\to\your-clone --in-place
   ```
   Optional: `--remote-name engismart` (name the host uses) and `--base-href /mf1/engismart/` (sets `baseHref` and `deployUrl` in `angular.json`:
   the template still carries the path of another app, `/mf1/ml-accelerator/`; ask the platform team which path this remote gets).
3. It prints what it did (files copied and edited). Running it again changes nothing ("already"). A line `UNCHANGED` or `MISSING` means: send me that line.
4. `npm install`, then `npm run build`.

## B. By hand (what the tool does)
* Copy `src/app/engismart/` into `src/app/`.
* `federation.config.js`: `name: 'engismart'` and `exposes: { './Routes': './src/app/app.routes.ts' }`.
* `src/app/app.routes.ts`: `export { engismartRoutes as routes } from './engismart/engismart.routes';`
* `src/app/app.config.ts` (stand-alone use only): `provideHttpClient(withInterceptors([devTokenInterceptor]))` with the import from `./engismart/core/dev-token.interceptor`.
* `src/app/app.html`: only `<router-outlet />`.
* every `src/environments/environment*.ts`: add `engismartUrl: '<backend address>'` (the platform API address the two Engismart backend modules hang under, e.g. `https://host/engismart/api/v1`; the remote appends `/engismart_chat` and `/engismart_ingestion`).
* `package.json`: add `"marked": "^15.0.0"` and `"dompurify": "^3.2.0"`.

## What the host must do
* Register the remote (`environment.remoteList`) and load `./Routes` (see ENGISMART_START_HERE.md).
* Attach the token: the host's HTTP interceptor adds `access-token` to every `HttpClient` call to `engismartUrl`. This remote has no login code.
* Give people the Engismart application and a role in the platform (see the backend notes); Chat is for everyone, Manage and Users are shown only to developers
  (the backend enforces it as well).

## Screens
Chat (conversations, streaming answers, sources with pictures, image attachments), Manage knowledge (library, document detail, sheet preview with pictures in their cells and
corrections, records, pictures, search chunks, add documents with "new or update" suggestions), Users & usage (usage per person, domain limits).
