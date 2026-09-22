import { Component, OnInit, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { Passkey, RentshieldApiService } from '../services/rentshield-api.service'
import { ToastService } from 'src/app/services/toast.service'
import { firstValueFrom } from 'rxjs'
import { ConfirmButtonComponent } from '../../components/common/confirm-button/confirm-button.component'

// ZITADEL migration (2026-09-22) -- rewritten against
// RentshieldApiService's passkey methods (documents/security/passkeys/*
// in rentshield_views.py), replacing the now fully-broken
// AutheliaSecurityService (it called environment.autheliaApiUrl, which
// pointed at the Authelia backend deleted earlier this session).
// Dropped, not ported: renaming a passkey (ZITADEL's API has no
// rename/update RPC at all) and the password-change form (RentShield
// has no passwords any more) -- see rentshield_passkeys_view's own
// comment on why the Authelia-specific email "elevation" gate isn't
// needed either.
@Component({
  selector: 'pngx-account-security',
  templateUrl: './account-security.component.html',
  imports: [FormsModule, NgxBootstrapIconsModule, ConfirmButtonComponent],
})
export class AccountSecurityComponent implements OnInit {
  readonly loading = signal(false)
  readonly passkeys = signal<Passkey[]>([])

  newPasskeyDescription = ''
  readonly addingPasskey = signal(false)

  constructor(
    private api: RentshieldApiService,
    private toastService: ToastService
  ) {}

  ngOnInit(): void {
    this.handleReturnFromAddPasskey()
    this.load()
  }

  // The bridge page (zitadel/nginx/rentshield-bridge/index.html) always
  // redirects back here with ?passkeyAdded=1 on success, and never with
  // an error param -- a failed ceremony shows its own inline error and
  // stays on the bridge page (see its own "Cancel and go back" link),
  // it doesn't redirect back at all. So there's only one case to strip
  // from the URL here, unlike the old Authelia version's two.
  private handleReturnFromAddPasskey(): void {
    const params = new URLSearchParams(window.location.search)
    if (!params.has('passkeyAdded')) return
    this.toastService.showInfo($localize`Passkey added`)
    params.delete('passkeyAdded')
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
      const passkeys = await firstValueFrom(this.api.listPasskeys())
      this.passkeys.set(passkeys ?? [])
    } catch (error) {
      this.toastService.showError(
        $localize`Unable to load your passkeys`,
        error
      )
    } finally {
      this.loading.set(false)
    }
  }

  async addPasskey(): Promise<void> {
    const description = this.newPasskeyDescription.trim()
    if (!description) return
    this.addingPasskey.set(true)
    try {
      const returnTo = `${window.location.origin}${window.location.pathname}`
      const { redirect_url } = await firstValueFrom(
        this.api.startAddPasskey(description, returnTo)
      )
      window.location.href = redirect_url
    } catch (error) {
      this.toastService.showError($localize`Unable to start passkey registration`, error)
      this.addingPasskey.set(false)
    }
  }

  async deletePasskey(id: string): Promise<void> {
    try {
      await firstValueFrom(this.api.deletePasskey(id))
      await this.load()
      this.toastService.showInfo($localize`Passkey removed`)
    } catch (error) {
      this.toastService.showError($localize`Unable to remove passkey`, error)
    }
  }
}
