const base_url = new URL(document.baseURI)

export const DEFAULT_APP_TITLE = 'Paperless-ngx'

export const environment = {
  production: true,
  apiBaseUrl: document.baseURI + 'api/',
  apiVersion: '10', // match src/paperless/settings.py
  appTitle: DEFAULT_APP_TITLE,
  tag: 'prod',
  version: '3.1.2',
  webSocketHost: window.location.host,
  webSocketProtocol: window.location.protocol == 'https:' ? 'wss:' : 'ws:',
  webSocketBaseUrl: base_url.pathname + 'ws/',
  // A real deployment's Authelia domain -- not derivable from
  // document.baseURI the way apiBaseUrl is, since Authelia lives on its
  // own subdomain (see authelia/configuration.yml). Replace at deploy
  // time; must share a parent domain with wherever this app is served
  // (see that file's session.cookies comment for why).
  autheliaApiUrl: 'https://auth.rentshield.local:9091',
  autheliaBridgeUrl: 'https://auth.rentshield.local:9091/rentshield-bridge/index.html',
}
