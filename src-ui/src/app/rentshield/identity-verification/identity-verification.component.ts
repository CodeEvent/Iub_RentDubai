import { CommonModule } from '@angular/common'
import { Component, OnDestroy, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { Subscription, interval } from 'rxjs'
import { switchMap } from 'rxjs/operators'
import { RentshieldApiService } from '../services/rentshield-api.service'

type CaptureStep = 'idle' | 'awaiting_front' | 'awaiting_live' | 'processing'

// Property-owner identity verification. The capture itself (passport
// photo, then a selfie) happens right here, inside RentShield's own
// page -- backed by a self-hosted Idswyft instance
// (documents/rentshield_identity/) for the actual OCR/liveness/face-
// match work, but the property owner never leaves this page or sees
// Idswyft's own branding (their hosted page can't be white-labeled
// without an enterprise license -- see README).
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

  starting = signal(false)
  uploading = signal(false)
  error = signal<string | null>(null)
  status = signal<string | null>(null)
  step = signal<CaptureStep>('idle')

  private pollSubscription?: Subscription
  // Captured once via the browser's own Geolocation API when
  // verification starts -- evidence of where it happened for the admin
  // review page, never a gate on the result. Null (permission
  // denied/unsupported) is a normal, silently-accepted outcome, same as
  // this project's other optional-evidence fields.
  private position: GeolocationPosition | null = null

  constructor() {
    // A user who's already mid-verification (or already verified) from
    // a previous visit should resume at the right capture step
    // immediately, not a blank "start" button or a spinner with no way
    // forward -- that used to be lost on reload entirely.
    this.api.getIdentityVerificationStatus().subscribe((res) => {
      if (res.status) this.status.set(res.status)
      if (res.status === 'pending') {
        this.step.set(this.mapStep(res.step))
        this.startPolling()
      }
    })
  }

  ngOnDestroy(): void {
    this.pollSubscription?.unsubscribe()
  }

  private mapStep(rawStep: string | null): CaptureStep {
    switch (rawStep) {
      case 'AWAITING_FRONT':
        return 'awaiting_front'
      case 'AWAITING_LIVE':
        return 'awaiting_live'
      case 'FRONT_PROCESSING':
      case 'LIVE_PROCESSING':
      case 'FACE_MATCHING':
        return 'processing'
      default:
        // COMPLETE/HARD_REJECTED land here -- status() (final_result)
        // already carries the real outcome by the time this matters.
        return 'processing'
    }
  }

  // Reset is just start() again -- the backend already generates a
  // fresh Idswyft session and overwrites the stored one whenever it's
  // not already verified, so there's no separate "clear" step needed.
  reset(): void {
    this.pollSubscription?.unsubscribe()
    this.error.set(null)
    this.start()
  }

  start(): void {
    this.starting.set(true)
    this.error.set(null)
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => (this.position = position),
        () => (this.position = null),
        { timeout: 8000 }
      )
    }
    this.api.startIdentityVerification().subscribe({
      next: (res) => {
        this.starting.set(false)
        this.status.set(res.status)
        if (res.status === 'verified') return
        this.step.set(this.mapStep(res.step))
      },
      error: (err) => {
        this.starting.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not start identity verification.')
      },
    })
  }

  onFrontFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    this.uploading.set(true)
    this.error.set(null)
    this.api.uploadIdentityFrontDocument(file, this.position).subscribe({
      next: (res) => {
        this.uploading.set(false)
        this.status.set(res.status)
        this.step.set(this.mapStep(res.step))
      },
      error: (err) => {
        this.uploading.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not process that photo -- try again.')
      },
    })
  }

  onSelfieFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    this.uploading.set(true)
    this.error.set(null)
    this.api.uploadIdentityLiveCapture(file, this.position).subscribe({
      next: (res) => {
        this.uploading.set(false)
        this.status.set(res.status)
        this.step.set(this.mapStep(res.step))
        if (res.status === 'pending') this.startPolling()
      },
      error: (err) => {
        this.uploading.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not process that selfie -- try again.')
      },
    })
  }

  private startPolling(): void {
    this.pollSubscription?.unsubscribe()
    this.pollSubscription = interval(4000)
      .pipe(switchMap(() => this.api.getIdentityVerificationStatus()))
      .subscribe((res) => {
        this.status.set(res.status)
        if (res.status !== 'pending') {
          this.pollSubscription?.unsubscribe()
        } else {
          this.step.set(this.mapStep(res.step))
        }
      })
  }
}
