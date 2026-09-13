import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { PermissionsService } from 'src/app/services/permissions.service'
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
// Fixed (2026-09-13): the nav link used to gate on isAdmin() alone,
// which broke the moment the seeded `notary` account was correctly
// stripped of is_staff/is_superuser (a real over-privilege bug found
// separately -- see roles.py's create_rentshield_roles.py comment) --
// app-frame.component.ts now also checks a real is_notary_public flag
// (documents/rentshield_identity/admin_views.py's notary_status_view)
// fetched once at app load, not tied to is_staff at all.
//
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
  permissionsService = inject(PermissionsService)

  records = signal<AdminVerificationRecord[]>([])
  loading = signal(true)
  error = signal<string | null>(null)
  showAll = signal(false)
  // Reviews one record at a time (the riskiest first -- the backend
  // already sorts the needs-review queue that way) instead of a long
  // list to scroll through. Confirm/reject reloads the queue, so the
  // next-riskiest record is simply whatever's now first -- no manual
  // "next" bookkeeping needed. Only meaningful for the live queue, not
  // the full history (showAll) view.
  focusMode = signal(false)
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

  toggleFocusMode(): void {
    this.focusMode.set(!this.focusMode())
  }

  // What actually renders -- just the top (riskiest) record in focus
  // mode, the full queue otherwise.
  visibleRecords(): AdminVerificationRecord[] {
    if (this.focusMode() && !this.showAll() && this.records().length > 0) {
      return [this.records()[0]]
    }
    return this.records()
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

  // Claude's own advisory summary (ai_prescreen.py) ends with a
  // "Likely outcome: <label>" line -- pulled out here so it can render
  // as a scannable badge instead of buried in a paragraph of prose.
  // Falls back to no badge (just the plain text) for a summary
  // generated before this line existed.
  outcomeFromSummary(summary: string): { label: string; cls: string } | null {
    const match = summary.match(/Likely outcome:\s*(.+)/i)
    if (!match) return null
    const label = match[1].trim()
    const lower = label.toLowerCase()
    const cls = lower.startsWith('significant')
      ? 'text-bg-danger'
      : lower.startsWith('minor')
        ? 'text-bg-warning'
        : 'text-bg-success'
    return { label, cls }
  }

  summaryWithoutOutcome(summary: string): string {
    return summary.replace(/Likely outcome:\s*.+/i, '').trim()
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
        // Reload rather than patch in place -- this also makes focus
        // mode's auto-advance work for free (the next call just shows
        // records()[0], whatever that now is) and picks up fields a
        // local patch never touched (notary_reviewed_by/at/notes).
        next: () => {
          this.setBusy(record.id, false)
          this.loadRecords()
        },
        error: (err) => this.handleReviewError(record.id, err),
      })
  }

  reject(record: AdminVerificationRecord): void {
    this.setBusy(record.id, true)
    this.api
      .rejectIdentityVerification(record.id, this.reviewNotes[record.id] || '', this.editsFor(record.id))
      .subscribe({
        next: () => {
          this.setBusy(record.id, false)
          this.loadRecords()
        },
        error: (err) => this.handleReviewError(record.id, err),
      })
  }

  // Admin-only (see admin_reset_verification_view's own docstring for
  // why this is deliberately not something a Notary can do) -- wipes
  // every uploaded file and every OCR/chip/declared field back to a
  // clean slate so the user can redo the whole pipeline from scratch.
  // Real destructive action, confirmed before firing.
  resetVerification(record: AdminVerificationRecord): void {
    if (!confirm(`Reset ${record.username}'s identity verification? This permanently deletes every photo/video they've uploaded so far.`)) {
      return
    }
    this.setBusy(record.id, true)
    this.api.resetIdentityVerification(record.id).subscribe({
      // Reload rather than patch the record in place -- every OCR/chip/
      // declared field and every photo/video URL changed (cleared), not
      // just `status`, so a local patch would leave stale thumbnails and
      // text showing next to the now-correct status.
      next: () => {
        this.setBusy(record.id, false)
        this.loadRecords()
      },
      error: (err) => this.handleReviewError(record.id, err),
    })
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
