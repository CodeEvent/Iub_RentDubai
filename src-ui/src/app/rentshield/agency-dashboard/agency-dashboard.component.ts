import { CommonModule } from '@angular/common'
import { HttpErrorResponse } from '@angular/common/http'
import { Component, OnInit, inject, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { Router, RouterModule } from '@angular/router'
import { NgbPopoverModule } from '@ng-bootstrap/ng-bootstrap'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { firstValueFrom } from 'rxjs'
import { PageHeaderComponent } from 'src/app/components/common/page-header/page-header.component'
import { WidgetFrameComponent } from 'src/app/components/dashboard/widgets/widget-frame/widget-frame.component'
import { ToastService } from 'src/app/services/toast.service'
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
    FormsModule,
    RouterModule,
    NgbPopoverModule,
    NgxBootstrapIconsModule,
    PageHeaderComponent,
    WidgetFrameComponent,
  ],
  templateUrl: './agency-dashboard.component.html',
  styleUrl: './agency-dashboard.component.scss',
})
export class AgencyDashboardComponent implements OnInit {
  private api = inject(RentshieldApiService)
  private router = inject(Router)
  private toastService = inject(ToastService)

  readonly loading = signal(true)
  readonly dashboard = signal<OrganizationDashboard | null>(null)

  inviteEmail = ''
  readonly inviting = signal(false)

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

  async inviteTeammate(): Promise<void> {
    const email = this.inviteEmail.trim()
    if (!email) return
    this.inviting.set(true)
    try {
      await firstValueFrom(this.api.inviteTeammate(email))
      this.toastService.showInfo($localize`Invite sent to ${email}`)
      this.inviteEmail = ''
    } catch (error) {
      const message =
        error instanceof HttpErrorResponse && error.error?.error
          ? error.error.error
          : $localize`Unable to send that invite`
      this.toastService.showError(message)
    } finally {
      this.inviting.set(false)
    }
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
