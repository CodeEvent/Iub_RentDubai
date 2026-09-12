import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { AdminVerificationRecord, RentshieldApiService } from '../services/rentshield-api.service'

// Admin-only review page: every property owner who has gone through
// identity verification, their submitted passport photo and selfie
// side by side, the result, and where it was performed (if the browser
// granted location access). Route itself is admin-gated in
// app-routing.module.ts's data.requiredPermission the same way other
// admin pages are; the backend (documents/rentshield_identity/
// admin_views.py) enforces the real check regardless.
@Component({
  selector: 'app-identity-admin',
  standalone: true,
  imports: [CommonModule, NgxBootstrapIconsModule],
  templateUrl: './identity-admin.component.html',
  styleUrl: './identity-admin.component.scss',
})
export class IdentityAdminComponent {
  private api = inject(RentshieldApiService)

  records = signal<AdminVerificationRecord[]>([])
  loading = signal(true)
  error = signal<string | null>(null)

  constructor() {
    this.api.getIdentityVerificationAdminList().subscribe({
      next: (res) => {
        this.records.set(res.results)
        this.loading.set(false)
      },
      error: (err) => {
        this.loading.set(false)
        this.error.set(err?.error?.error || err?.message || 'Could not load verification records.')
      },
    })
  }

  statusClass(status: string): string {
    switch (status) {
      case 'verified':
        return 'text-bg-success'
      case 'failed':
        return 'text-bg-danger'
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
}
