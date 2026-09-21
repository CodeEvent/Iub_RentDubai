// This file can be replaced during build by using the `fileReplacements` array.
// `ng build --configuration production` replaces `environment.ts` with `environment.prod.ts`.
// The list of file replacements can be found in `angular.json`.

export const DEFAULT_APP_TITLE = 'Paperless-ngx'

export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000/api/',
  apiVersion: '10',
  appTitle: DEFAULT_APP_TITLE,
  tag: 'dev',
  version: 'DEVELOPMENT',
  webSocketHost: 'localhost:8000',
  webSocketProtocol: 'ws:',
  webSocketBaseUrl: '/ws/',
  // Direct calls (list/rename/delete passkey, elevation, change
  // password) -- reachable cross-origin-but-same-site now that both
  // domains share the parent 'rentshield.local' (see
  // authelia/configuration.yml's session.cookies comment).
  autheliaApiUrl: 'https://auth.rentshield.local:9091',
  // Only "add a passkey" redirects here -- the one action that can't
  // run as a direct call, see authelia/nginx/rentshield-bridge/index.html.
  autheliaBridgeUrl: 'https://auth.rentshield.local:9091/rentshield-bridge/index.html',
}
