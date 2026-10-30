# Engismart is already inside this Angular remote

This folder is the Chromosome Angular remote template (`mfe-boilerplate-code`) with the Engismart screens added.
The template was changed only in: `federation.config.js`, `src/app/app.routes.ts`, `src/app/app.config.ts` (a developer-only token helper),
`src/app/app.html`, `src/app/app.scss`, `src/environments/*.ts` (one new line `engismartUrl`) and `package.json` (two libraries: `marked`, `dompurify`).
Engismart itself is in `src/app/engismart/`. More notes: `docs/engismart/`.

## Your steps (about 20 minutes, no coding)
1. `npm install` (first time it also refreshes `package-lock.json`).
2. Open `src/environments/environment*.ts` and check the line `engismartUrl`: it is the address of the Engismart backend for that environment
   (platform gateway + `/engismart/api/v1` is an assumption: ask the team for the real path). The remote adds `/engismart_chat` and
   `/engismart_ingestion` to it itself (the backend's two modules).
3. Build: `npm run build` (add `-- --configuration=staging` etc. as your pipeline does).
4. Tell the host about the remote: in the host's `environment.remoteList` add `engismart: '<where it is deployed>/remoteEntry.json'`
   (the name must equal `name` in `federation.config.js`), and add a host route that loads it:
   `loadRemoteModule('engismart', './Routes').then(m => m.routes)`.
5. The backend login: the host's HTTP interceptor must add the platform token (header `access-token`) to calls to `engismartUrl`.
   Everything in this remote goes through Angular's `HttpClient`, including the chat stream and the picture files, so one interceptor covers all.

## Run it on its own (without the host), for a quick look
Start the backend, then `npm run build` and open the built `dist/.../browser` folder with any static web server. In the browser console run
`localStorage.setItem('engismart.devToken', '<a platform token>')` and reload. This token helper exists only in `app.config.ts`, which the host never loads.

If a step fails, send me the error text.
