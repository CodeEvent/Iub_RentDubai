import { CommonModule } from '@angular/common'
import { Component, OnInit, inject, signal } from '@angular/core'
import { Router, RouterModule } from '@angular/router'
import { NgbPopoverModule } from '@ng-bootstrap/ng-bootstrap'
import { PageHeaderComponent } from 'src/app/components/common/page-header/page-header.component'
import { WidgetFrameComponent } from 'src/app/components/dashboard/widgets/widget-frame/widget-frame.component'
import {
  OrganizationDashboard,
  RentshieldApiService,
} from '../services/rentshield-api.service'

// Primary entry screen for a B2B Organization's team (2026-09-22) --
// aggregate stats scoped to the logged-in user's own Organization, via
// GET /api/documents/organization/dashboard/ (see that view's own
// docstring in rentshield_views.py for why status_breakdown is a count
// per real pipeline-stage tag, not an invented linear status enum, and
// why upcoming_deadlines is notice_date + notice_period_days, not
// upload date). Route itself carries no guard: an individual account
// landing here (stale link, direct URL) just gets 404'd by the backend
// and redirected below, same as app-frame.component.ts hides the nav
// link entirely for that case via isOrganizationMember.
@Component({
  selector: 'app-agency-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    NgbPopoverModule,
    PageHeaderComponent,
    WidgetFrameComponent,
  ],
  templateUrl: './agency-dashboard.component.html',
  styleUrl: './agency-dashboard.component.scss',
})
export class AgencyDashboardComponent implements OnInit {
  private api = inject(RentshieldApiService)
  private router = inject(Router)

  readonly loading = signal(true)
  readonly dashboard = signal<OrganizationDashboard | null>(null)

  ngOnInit(): void {
    this.api.getOrganizationDashboard().subscribe({
      next: (res) => {
        this.dashboard.set(res)
        this.loading.set(false)
      },
      error: () => {
        this.router.navigate(['/dashboard'])
      },
    })
  }

  statusBadgeClass(daysRemaining: number): string {
    if (daysRemaining < 0) return 'bg-danger'
    if (daysRemaining <= 7) return 'bg-danger'
    if (daysRemaining <= 30) return 'bg-warning text-dark'
    return 'bg-secondary'
  }

  totalStatusCount(): number {
    return (
      this.dashboard()?.status_breakdown.reduce((sum, row) => sum + row.count, 0) ?? 0
    )
  }

  statusPercent(count: number): number {
    const total = this.totalStatusCount()
    return total > 0 ? (count / total) * 100 : 0
  }
}
