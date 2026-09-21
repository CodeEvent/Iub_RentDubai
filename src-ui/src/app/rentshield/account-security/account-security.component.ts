import { Component, OnInit, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import {
  AutheliaUserInfo,
  AutheliaWebAuthnCredential,
} from 'src/app/data/authelia-security'
import { AutheliaSecurityService } from 'src/app/services/authelia-security.service'
import { ToastService } from 'src/app/services/toast.service'
import { environment } from 'src/environments/environment'
import { ConfirmButtonComponent } from '../../components/common/confirm-button/confirm-button.component'

@Component({
  selector: 'pngx-account-security',
  templateUrl: './account-security.component.html',
  imports: [FormsModule, NgxBootstrapIconsModule, ConfirmButtonComponent],
})
export class AccountSecurityComponent implements OnInit {
  readonly loading = signal(false)
  readonly userInfo = signal<AutheliaUserInfo>(undefined)
  readonly credentials = signal<AutheliaWebAuthnCredential[]>([])

  readonly renamingId = signal<number | null>(null)
  renameValue = ''

  newPasskeyDescription = ''

  readonly changingPassword = signal(false)
  oldPassword = ''
  newPassword = ''
  newPasswordConfirm = ''

  // Set only while an action is waiting on the emailed identity-
  // verification code -- resolved/rejected by submitElevationCode().
  readonly elevationPending = signal(false)
  elevationCode = ''
  private pendingElevatedAction: (() => Promise<void>) | null = null

  constructor(
    private security: AutheliaSecurityService,
    private toastService: ToastService
  ) {}

  ngOnInit(): void {
    this.handleReturnFromAddPasskey()
    this.load()
  }

  // "Add a passkey" redirects out to auth.rentshield.local and back
  // (see authelia/nginx/rentshield-bridge/index.html) -- pick up the
  // result here and strip it from the URL.
  private handleReturnFromAddPasskey(): void {
    const params = new URLSearchParams(window.location.search)
    if (params.has('passkeyAdded')) {
      this.toastService.showInfo($localize`Passkey added`)
    } else if (params.has('passkeyError')) {
      this.toastService.showError(
        $localize`Unable to add passkey`,
        params.get('passkeyError')
      )
    } else {
      return
    }
    params.delete('passkeyAdded')
    params.delete('passkeyError')
    const query = params.toString()
    window.history.replaceState(
      {},
      '',
      window.location.pathname + (query ? `?${query}` : '')
    )
  }

  async load(): Promise<void> {
    this.loading.set(true)
    try {
      const [userInfo, credentials] = await Promise.all([
        this.security.getUserInfo(),
        this.security.listCredentials(),
      ])
      this.userInfo.set(userInfo)
      this.credentials.set(credentials ?? [])
    } catch (error) {
      this.toastService.showError(
        $localize`Unable to load your account security settings`,
        error
      )
    } finally {
      this.loading.set(false)
    }
  }

  startRename(credential: AutheliaWebAuthnCredential): void {
    this.renamingId.set(credential.id)
    this.renameValue = credential.description
  }

  cancelRename(): void {
    this.renamingId.set(null)
  }

  async confirmRename(id: number): Promise<void> {
    const description = this.renameValue.trim()
    if (!description) return
    try {
      await this.runElevated(() =>
        this.security.renameCredential(id, description)
      )
      this.renamingId.set(null)
      await this.load()
      this.toastService.showInfo($localize`Passkey renamed`)
    } catch (error) {
      this.toastService.showError($localize`Unable to rename passkey`, error)
    }
  }

  async deleteCredential(id: number): Promise<void> {
    try {
      await this.runElevated(() => this.security.deleteCredential(id))
      await this.load()
      this.toastService.showInfo($localize`Passkey removed`)
    } catch (error) {
      this.toastService.showError($localize`Unable to remove passkey`, error)
    }
  }

  // Unlike every other action here, this ends in a same-tab redirect,
  // not a direct call -- browsers only allow the WebAuthn "create
  // credential" ceremony to run in a document served by Authelia
  // itself, no matter what domain called into it (see the bridge page's
  // own comment). The bridge page has no elevation UI of its own
  // (registration requires an elevated session), so that has to happen
  // here, first, through the same "Confirm it's you" modal every other
  // action already uses -- otherwise the redirect would just land on a
  // dead-end error with no way to enter a code at all.
  async addPasskey(): Promise<void> {
    const description = this.newPasskeyDescription.trim()
    if (!description) return
    // runElevated only elevates in reaction to an ELEVATION_REQUIRED
    // throw, so the guard here has to actually check status and throw
    // it itself -- a real API call, not the navigation, needs to be
    // what runElevated retries, since navigating away is a one-way trip
    // with no chance to react to a 403 afterwards.
    await this.runElevated(async () => {
      const status = await this.security.getElevationStatus()
      if (!status.elevated) throw new Error('ELEVATION_REQUIRED')
    })
    const returnTo = `${window.location.origin}${window.location.pathname}`
    const url = new URL(environment.autheliaBridgeUrl)
    url.searchParams.set('description', description)
    url.searchParams.set('return', returnTo)
    window.location.href = url.toString()
  }

  async changePassword(): Promise<void> {
    if (
      !this.oldPassword ||
      !this.newPassword ||
      this.newPassword !== this.newPasswordConfirm
    ) {
      return
    }
    this.changingPassword.set(true)
    try {
      await this.runElevated(() =>
        this.security.changePassword(this.oldPassword, this.newPassword)
      )
      this.oldPassword = ''
      this.newPassword = ''
      this.newPasswordConfirm = ''
      this.toastService.showInfo($localize`Password changed`)
    } catch (error) {
      this.toastService.showError($localize`Unable to change password`, error)
    } finally {
      this.changingPassword.set(false)
    }
  }

  // Runs `action`; if Authelia reports the session isn't elevated yet,
  // requests an identity-verification email code, waits for the user to
  // submit it via submitElevationCode(), then retries `action` once.
  private async runElevated(action: () => Promise<any>): Promise<any> {
    try {
      return await action()
    } catch (error) {
      if (error?.message !== 'ELEVATION_REQUIRED') throw error
    }

    await this.security.startElevation()
    this.toastService.showInfo(
      $localize`We've emailed you a one-time code to confirm this change`
    )
    return new Promise((resolve, reject) => {
      this.pendingElevatedAction = async () => {
        try {
          resolve(await action())
        } catch (error) {
          reject(error)
        }
      }
      this.elevationPending.set(true)
    })
  }

  async submitElevationCode(): Promise<void> {
    const code = this.elevationCode.trim()
    if (!code || !this.pendingElevatedAction) return
    try {
      await this.security.verifyElevation(code)
      this.elevationCode = ''
      this.elevationPending.set(false)
      const action = this.pendingElevatedAction
      this.pendingElevatedAction = null
      await action()
    } catch (error) {
      this.toastService.showError(
        $localize`That code didn't work. Please try again.`,
        error
      )
    }
  }

  cancelElevation(): void {
    this.elevationPending.set(false)
    this.pendingElevatedAction = null
    this.elevationCode = ''
  }
}
