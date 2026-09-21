import { HttpClient, HttpErrorResponse } from '@angular/common/http'
import { Injectable, inject } from '@angular/core'
import { firstValueFrom } from 'rxjs'
import {
  AutheliaElevationStatus,
  AutheliaUserInfo,
  AutheliaWebAuthnCredential,
} from 'src/app/data/authelia-security'
import { environment } from 'src/environments/environment'

// Direct calls to Authelia's own REST API for everything the My Profile
// Security tab needs except "add a passkey" (see
// authelia/nginx/rentshield-bridge/index.html for why that one action
// alone can't be a direct call). Reachable cross-origin-but-same-site
// now that RentShield and Authelia share the parent domain
// 'rentshield.local' -- see authelia/configuration.yml's session.cookies
// comment -- with CORS opted into separately on Authelia's own nginx
// proxy (authelia/nginx/nginx.conf).
@Injectable({
  providedIn: 'root',
})
export class AutheliaSecurityService {
  private http = inject(HttpClient)

  private url(path: string): string {
    return `${environment.autheliaApiUrl}${path}`
  }

  private async request<T>(
    method: 'GET' | 'PUT' | 'POST' | 'DELETE',
    path: string,
    body?: any
  ): Promise<T> {
    try {
      const response = await firstValueFrom(
        this.http.request<{ status: string; data: T }>(method, this.url(path), {
          body,
          withCredentials: true,
        })
      )
      return response.data
    } catch (error) {
      if (
        error instanceof HttpErrorResponse &&
        error.status === 403 &&
        error.error?.data?.elevation !== undefined
      ) {
        throw new Error('ELEVATION_REQUIRED')
      }
      // Rethrow the real HttpErrorResponse, not a wrapped plain Error --
      // ToastService's toast component only shows status/url/message
      // detail for objects shaped like one (isDetailedError()); a bare
      // Error loses all of that (and even JSON.stringifies to '{}').
      throw error
    }
  }

  getUserInfo(): Promise<AutheliaUserInfo> {
    return this.request('GET', '/api/user/info')
  }

  listCredentials(): Promise<AutheliaWebAuthnCredential[]> {
    return this.request('GET', '/api/secondfactor/webauthn/credentials')
  }

  renameCredential(id: number, description: string): Promise<void> {
    return this.request('PUT', `/api/secondfactor/webauthn/credential/${id}`, {
      description,
    })
  }

  deleteCredential(id: number): Promise<void> {
    return this.request('DELETE', `/api/secondfactor/webauthn/credential/${id}`)
  }

  // Unlike the other endpoints above, this one always returns 200 (with
  // elevated: false) rather than a 403 when not elevated -- it reports
  // status, it doesn't gate on it. Used as an explicit pre-check before
  // the "Add a passkey" redirect, which has no way to react to a 403
  // once the browser has already navigated away.
  getElevationStatus(): Promise<AutheliaElevationStatus> {
    return this.request('GET', '/api/user/session/elevation')
  }

  startElevation(): Promise<{ delete_id: string }> {
    return this.request('POST', '/api/user/session/elevation')
  }

  verifyElevation(code: string): Promise<void> {
    return this.request('PUT', '/api/user/session/elevation', { otc: code })
  }

  changePassword(oldPassword: string, newPassword: string): Promise<void> {
    return this.request('POST', '/api/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  }
}
