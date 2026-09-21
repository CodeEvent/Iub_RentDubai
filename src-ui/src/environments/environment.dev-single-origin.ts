// Used by the `dev-single-origin` build configuration (ng build
// --configuration=dev-single-origin --watch), which outputs straight
// into src/documents/static/frontend/ and is served by Django itself
// on :8000 -- there is no separate :4200 origin in this mode, matching
// environment.prod.ts's build (same outputPath). The default
// environment.ts hardcodes apiBaseUrl to http://localhost:8000/api/,
// which is correct ONLY for the classic two-origin `ng serve` dev
// workflow (page on :4200, API on :8000) -- for this single-origin
// build it silently breaks the moment the page is loaded from any
// origin other than literally "localhost" itself (e.g. a phone on the
// LAN loading http://192.168.0.x:8000/: its own browser then tries to
// reach ITS OWN localhost:8000, which doesn't exist, producing an
// HttpErrorResponse with status 0 -- no server ever sees the request,
// so nothing server-side, including CORS/ALLOWED_HOSTS, could ever fix
// this). document.baseURI (same technique environment.prod.ts already
// uses) resolves to whatever origin actually served the page, so this
// works identically from localhost, a LAN IP, or a hostname.
const base_url = new URL(document.baseURI)

export const DEFAULT_APP_TITLE = 'Paperless-ngx'

export const environment = {
  production: false,
  apiBaseUrl: document.baseURI + 'api/',
  apiVersion: '10', // match src/paperless/settings.py
  appTitle: DEFAULT_APP_TITLE,
  tag: 'dev-single-origin',
  version: 'DEVELOPMENT',
  webSocketHost: window.location.host,
  webSocketProtocol: window.location.protocol == 'https:' ? 'wss:' : 'ws:',
  webSocketBaseUrl: base_url.pathname + 'ws/',
}
