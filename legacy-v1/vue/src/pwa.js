// Generates a Web App Manifest at runtime via a Blob URL, so "Add to
// Home Screen" on Android installs the app as standalone (no browser
// chrome, its own icon and splash) without needing a static manifest
// file served alongside the Vite build. Ported from the original
// single-file prototype's approach.
export function installManifest() {
  try {
    const icon = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230f172a'/%3E%3Cpath d='M32 10l17 6v13c0 12-7.5 20.5-17 25-9.5-4.5-17-13-17-25V16z' fill='%2310b981'/%3E%3Cpath d='M24 32l6 6 11-13' stroke='%230f172a' stroke-width='4' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E";
    const manifest = {
      name: 'Dubai Rent Shield',
      short_name: 'Rent Shield',
      description: 'Bilingual RERA-compliant eviction notice generator',
      start_url: location.href,
      display: 'standalone',
      background_color: '#f8fafc',
      theme_color: '#0f172a',
      icons: [{ src: icon, sizes: '64x64', type: 'image/svg+xml', purpose: 'any maskable' }]
    };
    const blob = new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' });
    const link = document.createElement('link');
    link.rel = 'manifest';
    link.href = URL.createObjectURL(blob);
    document.head.appendChild(link);
  } catch {
    // Manifest install is a progressive enhancement — never block the app on it.
  }
}
