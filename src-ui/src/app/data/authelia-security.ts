// Shapes confirmed against a real running Authelia v4.39.26 instance
// (curl'd with a live session cookie, and cross-checked against its own
// frontend source under /static/js/) -- not guessed from its OpenAPI
// summary alone.

export interface AutheliaWebAuthnCredential {
  id: number
  description: string
  created_at: string
  last_used_at: string | null
  attachment: string
  transports: string[]
  discoverable: boolean
}

export interface AutheliaUserInfo {
  display_name: string
  emails: string[]
  method: string
  has_totp: boolean
  has_webauthn: boolean
  has_duo: boolean
}

export interface AutheliaElevationStatus {
  elevated: boolean
  expires: number
  factor_knowledge: boolean
  require_second_factor: boolean
  skip_second_factor: boolean
  can_skip_second_factor: boolean
}

// The generic "you're missing X to do this" body Authelia's protected
// endpoints return as a 403 when not yet elevated.
export interface AutheliaAuthorizationError {
  elevation: boolean
  first_factor: boolean
  second_factor: boolean
}
