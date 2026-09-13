import { CommonModule } from '@angular/common'
import { Component, OnDestroy, inject, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { Subscription, interval } from 'rxjs'
import { switchMap } from 'rxjs/operators'
import { DeclaredDocument, RentshieldApiService } from '../services/rentshield-api.service'

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
  imports: [CommonModule, FormsModule, RouterModule, NgxBootstrapIconsModule],
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

  // "Declare your document" step -- shown after "Start Verification",
  // before the QR: typed on a real keyboard specifically to cut down
  // the CAN/document-number typos that kept happening when this was
  // only ever typed on the app's own small screen (see
  // pairing_views.py's _validate_declared_document). Required before a
  // QR is ever generated -- there is no "skip this and type it on the
  // phone instead" path anymore, by design.
  declaring = signal(false)
  documentType: 'passport' | 'cie' = 'passport'
  documentNumber = ''
  dateOfBirth = ''
  expiryDate = ''
  can = ''

  private statusPollSubscription?: Subscription
  private pairingPollSubscription?: Subscription

  constructor() {
    // A user who's already mid-verification (or already verified) from
    // a previous visit -- most likely from the app itself, since that's
    // the only place capture happens now -- should see that immediately,
    // not a blank "start" button.
    //
    // Real bug caught live: `status: "pending"` is ambiguous on its
    // own. start_verification_view sets it the moment the WEB PAGE
    // calls startIdentityVerification() -- before the app has scanned
    // anything -- so a user whose last visit got that far but never
    // actually paired a phone (or an account with a stale "pending" row
    // from before this pairing step existed at all) would land straight
    // on "continue on your phone" with no QR ever shown and nothing
    // that will ever resolve. Disambiguate by also checking whether a
    // pairing was actually claimed; only then is "pending" really
    // "the app is mid-capture, keep polling" rather than "start()"
    // was called but pairing never completed".
    this.api.getIdentityVerificationStatus().subscribe((res) => {
      if (!res.status) return
      if (res.status !== 'pending') {
        this.status.set(res.status)
        return
      }
      this.api.getDevicePairingStatus().subscribe((pairRes) => {
        if (pairRes.status === 'claimed') {
          this.status.set('pending')
          this.startStatusPolling()
        }
        // Otherwise leave status() unset so the normal "Start
        // Verification" button (and a fresh QR from there) shows,
        // instead of a dead-end message.
      })
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
    this.declaring.set(false)
    this.error.set(null)
    // Real bug caught live: without this, clicking "Reset and start
    // over" while status() was "pending" did nothing VISIBLE at all --
    // start() below just flips declaring() to true, but the template's
    // outer @if (!status() || status() === 'failed') guard around the
    // whole declare/QR panel was still false (status() was still
    // "pending"), so that panel stayed hidden no matter what declaring()
    // was set to.
    this.status.set(null)
    this.start()
  }

  start(): void {
    this.error.set(null)
    this.declaring.set(true)
  }

  // CAN must be exactly 6 digits -- immediate feedback here instead of
  // only finding out after a round trip (or worse, after the app
  // itself fails a PACE handshake with whatever got typed).
  canLooksValid(): boolean {
    return /^\d{6}$/.test(this.can)
  }

  submitDeclaration(): void {
    if (this.documentType === 'passport' && (!this.documentNumber || !this.dateOfBirth || !this.expiryDate)) {
      this.error.set('Fill in document number, date of birth, and expiry date.')
      return
    }
    if (this.documentType === 'cie' && (!this.documentNumber || !this.canLooksValid())) {
      this.error.set('Fill in the document number and a 6-digit CAN.')
      return
    }

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
    const declared: DeclaredDocument = {
      declared_document_type: this.documentType,
      declared_document_number: this.documentNumber,
      ...(this.documentType === 'passport'
        ? { declared_date_of_birth: this.dateOfBirth, declared_expiry_date: this.expiryDate }
        : { declared_can: this.can }),
    }
    this.api.startDevicePairing(declared).subscribe({
      next: (res) => {
        this.starting.set(false)
        this.declaring.set(false)
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
