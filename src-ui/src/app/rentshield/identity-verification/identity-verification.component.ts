import { CommonModule } from '@angular/common'
import { Component, OnDestroy, inject, signal } from '@angular/core'
import { DomSanitizer, SafeHtml } from '@angular/platform-browser'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { Subscription, interval } from 'rxjs'
import { switchMap } from 'rxjs/operators'
import { RentshieldApiService } from '../services/rentshield-api.service'
// Vendored (not npm) qrcode-generator -- see that file's own header
// comment for why. MIT-licensed, zero runtime deps, single file.
import qrcode from '../vendor-qrcode.js'

// Property-owner identity verification. This page never touches a
// passport photo or a selfie itself -- it only starts a session with a
// self-hosted Idswyft instance (documents/rentshield_identity/) and
// polls for the result. The actual capture happens on Idswyft's own
// hosted page, either right here (same device) or on a phone after
// scanning the QR code below, since a phone's camera is usually much
// better for photographing a passport than a laptop's webcam.
//
// Deliberately NOT NFC chip reading: that needs either a native app
// with hardware NFC access or a physical PC/SC reader, neither of which
// this project has -- see README's 2026-09-12 identity-verification
// section for the full reasoning.
@Component({
  selector: 'app-identity-verification',
  standalone: true,
  imports: [CommonModule, RouterModule, NgxBootstrapIconsModule],
  templateUrl: './identity-verification.component.html',
  styleUrl: './identity-verification.component.scss',
})
export class IdentityVerificationComponent implements OnDestroy {
  private api = inject(RentshieldApiService)
  private sanitizer = inject(DomSanitizer)

  starting = signal(false)
  error = signal<string | null>(null)
  status = signal<string | null>(null)
  hostedUrl = signal<string | null>(null)
  qrSvg = signal<SafeHtml | null>(null)

  private pollSubscription?: Subscription

  constructor() {
    // A user who's already mid-verification (or already verified) from
    // a previous visit should see that state immediately, not a blank
    // "start" button.
    this.api.getIdentityVerificationStatus().subscribe((res) => {
      if (res.status) this.status.set(res.status)
      if (res.status === 'pending') this.startPolling()
    })
  }

  ngOnDestroy(): void {
    this.pollSubscription?.unsubscribe()
  }

  start(): void {
    this.starting.set(true)
    this.error.set(null)
    this.api.startIdentityVerification().subscribe({
      next: (res) => {
        this.starting.set(false)
        this.status.set(res.status)
        if (res.status === 'verified') return
        this.hostedUrl.set(res.hosted_url)
        this.renderQr(res.hosted_url)
        this.startPolling()
      },
      error: (err) => {
        this.starting.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not start identity verification.')
      },
    })
  }

  private renderQr(url: string): void {
    const qr = qrcode(0, 'M')
    qr.addData(url)
    qr.make()
    this.qrSvg.set(this.sanitizer.bypassSecurityTrustHtml(qr.createSvgTag(6)))
  }

  private startPolling(): void {
    this.pollSubscription?.unsubscribe()
    this.pollSubscription = interval(4000)
      .pipe(switchMap(() => this.api.getIdentityVerificationStatus()))
      .subscribe((res) => {
        this.status.set(res.status)
        if (res.status !== 'pending') this.pollSubscription?.unsubscribe()
      })
  }
}
