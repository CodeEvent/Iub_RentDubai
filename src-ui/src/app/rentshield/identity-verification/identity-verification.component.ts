import { CommonModule } from '@angular/common'
import { Component, OnDestroy, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { Subscription, interval } from 'rxjs'
import { switchMap } from 'rxjs/operators'
import { RentshieldApiService } from '../services/rentshield-api.service'

interface PairingState {
  code: string
  qrDataUri: string
  apkUrl: string | null
}

// Property-owner identity verification. Real NFC chip reading (ICAO
// 9303 PACE/BAC) needs a native app -- no browser on any platform can
// do it -- so this page's own job is just to get the property owner
// onto that app, authenticated as themself, via a QR code ("scan to
// sign in", documents/rentshield_identity/pairing_views.py) instead of
// typing a password on their phone. Everything past that (card photo,
// NFC tap, selfie, video, Notary review) happens entirely in the app;
// this page just reflects where that process currently stands by
// polling the same status endpoint the app's own progress updates,
// same mechanism as before this page stopped doing its own capture.
@Component({
  selector: 'app-identity-verification',
  standalone: true,
  imports: [CommonModule, RouterModule, NgxBootstrapIconsModule],
  templateUrl: './identity-verification.component.html',
  styleUrl: './identity-verification.component.scss',
})
export class IdentityVerificationComponent implements OnDestroy {
  private api = inject(RentshieldApiService)

  starting = signal(false)
  error = signal<string | null>(null)
  status = signal<string | null>(null)
  pairing = signal<PairingState | null>(null)
  pairingStatus = signal<string | null>(null)

  private statusPollSubscription?: Subscription
  private pairingPollSubscription?: Subscription

  constructor() {
    // A user who's already mid-verification (or already verified) from
    // a previous visit -- most likely from the app itself, since that's
    // the only place capture happens now -- should see that immediately,
    // not a blank "start" button.
    this.api.getIdentityVerificationStatus().subscribe((res) => {
      if (res.status) this.status.set(res.status)
      if (res.status === 'pending') this.startStatusPolling()
    })
  }

  ngOnDestroy(): void {
    this.statusPollSubscription?.unsubscribe()
    this.pairingPollSubscription?.unsubscribe()
  }

  reset(): void {
    this.statusPollSubscription?.unsubscribe()
    this.pairingPollSubscription?.unsubscribe()
    this.pairing.set(null)
    this.pairingStatus.set(null)
    this.error.set(null)
    this.start()
  }

  start(): void {
    this.starting.set(true)
    this.error.set(null)
    // Ensures an IdentityVerification row (and Idswyft session) exists
    // for this user before the app ever touches it -- the app's own
    // startVerification() call is a no-op get_or_create on top of this,
    // matching the resume-safe pattern already used elsewhere here.
    this.api.startIdentityVerification().subscribe({
      next: (res) => {
        if (res.status === 'verified') {
          this.starting.set(false)
          this.status.set(res.status)
          return
        }
        this.beginPairing()
      },
      error: (err) => {
        this.starting.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not start identity verification.')
      },
    })
  }

  private beginPairing(): void {
    this.api.startDevicePairing().subscribe({
      next: (res) => {
        this.starting.set(false)
        this.pairing.set({ code: res.code, qrDataUri: res.qr_data_uri, apkUrl: res.apk_url ?? null })
        this.pairingStatus.set('pending')
        this.startPairingPolling()
      },
      error: (err) => {
        this.starting.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not generate a sign-in code -- try again.')
      },
    })
  }

  private startPairingPolling(): void {
    this.pairingPollSubscription?.unsubscribe()
    this.pairingPollSubscription = interval(3000)
      .pipe(switchMap(() => this.api.getDevicePairingStatus()))
      .subscribe((res) => {
        this.pairingStatus.set(res.status)
        if (res.status === 'claimed') {
          this.pairingPollSubscription?.unsubscribe()
          this.status.set('pending')
          this.startStatusPolling()
        }
      })
  }

  private startStatusPolling(): void {
    this.statusPollSubscription?.unsubscribe()
    this.statusPollSubscription = interval(4000)
      .pipe(switchMap(() => this.api.getIdentityVerificationStatus()))
      .subscribe((res) => {
        this.status.set(res.status)
        if (res.status !== 'pending') {
          this.statusPollSubscription?.unsubscribe()
        }
      })
  }
}
