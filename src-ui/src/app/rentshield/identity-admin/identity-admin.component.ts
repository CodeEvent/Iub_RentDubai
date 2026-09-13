import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { AdminVerificationRecord, RentshieldApiService } from '../services/rentshield-api.service'

// Admin/Notary Public review page: every property owner who has gone
// through identity verification, their submitted passport photo,
// selfie, and confirmation video side by side, the card-OCR/NFC-chip
// cross-check, the automated result, and where it was performed (if
// the browser granted location access). Confirm/reject here is the
// only path that ever sets a verification to VERIFIED -- see
// IdentityVerification's own docstring for why. Route itself is
// admin-gated in app-routing.module.ts's data.requiredPermission the
// same way other admin pages are; the backend (documents/
// rentshield_identity/admin_views.py, IsRentshieldAdmin | IsNotaryPublic)
// enforces the real check regardless.
//
// Known gap: the frontend nav link/route still gate on isAdmin()
// (is_staff) alone, same as before this page could be reached by a
// non-staff Notary Public group member too -- fine today since every
// seeded Notary account happens to also be is_staff, but a real
// non-staff-only Notary account wouldn't see the nav link even though
// the backend would let them act. Fix: thread a real is_notary_public
// flag through UiSettings the same way is_staff already is.
// Fields the Notary can correct on the review page before deciding --
// keys match views.py's _NOTARY_EDITABLE_FIELDS, prefixed `edit_` on
// the wire (see confirmIdentityVerification/rejectIdentityVerification).
const EDITABLE_FIELDS = [
  'card_ocr_full_name',
  'card_ocr_date_of_birth',
  'card_ocr_document_number',
  'chip_full_name',
  'chip_date_of_birth',
  'chip_document_number',
] as const

@Component({
  selector: 'app-identity-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, NgxBootstrapIconsModule],
  templateUrl: './identity-admin.component.html',
  styleUrl: './identity-admin.component.scss',
})
export class IdentityAdminComponent {
  private api = inject(RentshieldApiService)

  records = signal<AdminVerificationRecord[]>([])
  loading = signal(true)
  error = signal<string | null>(null)
  showAll = signal(false)
  reviewNotes: Record<number, string> = {}
  // record id -> field name -> edited value, seeded from the record's
  // own OCR/chip values so the inputs start showing what's already
  // there, not blank boxes the Notary has to retype from scratch.
  editValues: Record<number, Record<string, string>> = {}
  busyIds = signal<Set<number>>(new Set())

  constructor() {
    this.loadRecords()
  }

  loadRecords(): void {
    this.loading.set(true)
    this.error.set(null)
    this.api.getIdentityVerificationAdminList(this.showAll()).subscribe({
      next: (res) => {
        this.records.set(res.results)
        for (const record of res.results) {
          if (this.isReviewable(record) && !this.editValues[record.id]) {
            this.editValues[record.id] = Object.fromEntries(
              EDITABLE_FIELDS.map((field) => [field, record[field] || ''])
            )
          }
        }
        this.loading.set(false)
      },
      error: (err) => {
        this.loading.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not load verification records.')
      },
    })
  }

  toggleShowAll(): void {
    this.showAll.set(!this.showAll())
    this.loadRecords()
  }

  statusClass(status: string): string {
    switch (status) {
      case 'verified':
        return 'text-bg-success'
      case 'failed':
        return 'text-bg-danger'
      case 'awaiting_notary_review':
        return 'text-bg-info'
      case 'manual_review':
        return 'text-bg-warning'
      default:
        return 'text-bg-secondary'
    }
  }

  mapLink(record: AdminVerificationRecord): string | null {
    if (record.latitude == null || record.longitude == null) return null
    return `https://www.openstreetmap.org/?mlat=${record.latitude}&mlon=${record.longitude}#map=16/${record.latitude}/${record.longitude}`
  }

  isReviewable(record: AdminVerificationRecord): boolean {
    return record.status === 'awaiting_notary_review'
  }

  isBusy(id: number): boolean {
    return this.busyIds().has(id)
  }

  private editsFor(id: number): Record<string, string> {
    const values = this.editValues[id] || {}
    return Object.fromEntries(Object.entries(values).map(([field, value]) => [`edit_${field}`, value]))
  }

  confirm(record: AdminVerificationRecord): void {
    this.setBusy(record.id, true)
    this.api
      .confirmIdentityVerification(record.id, this.reviewNotes[record.id] || '', this.editsFor(record.id))
      .subscribe({
        next: (res) => this.applyReviewResult(record, res.status),
        error: (err) => this.handleReviewError(record.id, err),
      })
  }

  reject(record: AdminVerificationRecord): void {
    this.setBusy(record.id, true)
    this.api
      .rejectIdentityVerification(record.id, this.reviewNotes[record.id] || '', this.editsFor(record.id))
      .subscribe({
        next: (res) => this.applyReviewResult(record, res.status),
        error: (err) => this.handleReviewError(record.id, err),
      })
  }

  private applyReviewResult(record: AdminVerificationRecord, status: string): void {
    record.status = status
    Object.assign(record, this.editValues[record.id])
    this.setBusy(record.id, false)
  }

  private handleReviewError(id: number, err: any): void {
    this.setBusy(id, false)
    this.error.set(err?.error?.error || err?.message || 'Could not record that review decision.')
  }

  private setBusy(id: number, busy: boolean): void {
    const next = new Set(this.busyIds())
    if (busy) next.add(id)
    else next.delete(id)
    this.busyIds.set(next)
  }
}
