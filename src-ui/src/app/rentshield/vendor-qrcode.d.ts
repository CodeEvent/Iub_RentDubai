// Companion declaration for vendor-qrcode.js -- TypeScript pairs a
// same-named .d.ts with a plain .js file automatically, no `allowJs`
// project-wide setting needed for this one vendored file.
interface QrCodeInstance {
  addData(data: string): void
  make(): void
  createSvgTag(cellSize?: number, margin?: number): string
}

declare function qrcode(typeNumber: number, errorCorrectionLevel: 'L' | 'M' | 'Q' | 'H'): QrCodeInstance

export default qrcode
