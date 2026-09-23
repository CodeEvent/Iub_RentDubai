import { CommonModule } from '@angular/common'
import { HttpErrorResponse } from '@angular/common/http'
import { Component, OnInit, computed, inject, signal } from '@angular/core'
import { FormsModule } from '@angular/forms'
import { Router, RouterModule } from '@angular/router'
import { NgbPopoverModule } from '@ng-bootstrap/ng-bootstrap'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { firstValueFrom } from 'rxjs'
import { ConfirmButtonComponent } from 'src/app/components/common/confirm-button/confirm-button.component'
import { PageHeaderComponent } from 'src/app/components/common/page-header/page-header.component'
import { WidgetFrameComponent } from 'src/app/components/dashboard/widgets/widget-frame/widget-frame.component'
import { SettingsService } from 'src/app/services/settings.service'
import { ToastService } from 'src/app/services/toast.service'
import {
  OrganizationDashboard,
  OrganizationMember,
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
    ConfirmButtonComponent,
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
  private settingsService = inject(SettingsService)

  readonly loading = signal(true)
  readonly dashboard = signal<OrganizationDashboard | null>(null)

  inviteEmail = ''
  readonly inviting = signal(false)

  readonly members = signal<OrganizationMember[]>([])
  readonly membersLoading = signal(true)
  readonly memberActionIds = signal<Set<number>>(new Set())

  memberSearch = ''
  private readonly memberSearchTerm = signal('')
  readonly filteredMembers = computed(() => {
    const term = this.memberSearchTerm().trim().toLowerCase()
    if (!term) return this.members()
    return this.members().filter(
      (member) =>
        member.username.toLowerCase().includes(term) ||
        member.email.toLowerCase().includes(term)
    )
  })

  onMemberSearchChange(): void {
    this.memberSearchTerm.set(this.memberSearch)
  }

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
    this.loadMembers()
  }

  private loadMembers(): void {
    this.membersLoading.set(true)
    this.api.listOrganizationMembers().subscribe({
      next: (members) => {
        this.members.set(members)
        this.membersLoading.set(false)
      },
      error: () => {
        this.membersLoading.set(false)
      },
    })
  }

  private errorMessage(error: unknown, fallback: string): string {
    return error instanceof HttpErrorResponse && error.error?.error
      ? error.error.error
      : fallback
  }

  async inviteTeammate(): Promise<void> {
    const email = this.inviteEmail.trim()
    if (!email) return
    this.inviting.set(true)
    try {
      await firstValueFrom(this.api.inviteTeammate(email))
      this.toastService.showInfo($localize`Invite sent to ${email}`)
      this.inviteEmail = ''
      this.loadMembers()
    } catch (error) {
      this.toastService.showError(this.errorMessage(error, $localize`Unable to send that invite`))
    } finally {
      this.inviting.set(false)
    }
  }

  isActingOn(memberId: number): boolean {
    return this.memberActionIds().has(memberId)
  }

  private setActing(memberId: number, acting: boolean): void {
    const next = new Set(this.memberActionIds())
    if (acting) next.add(memberId)
    else next.delete(memberId)
    this.memberActionIds.set(next)
  }

  async resendInvite(member: OrganizationMember): Promise<void> {
    this.setActing(member.id, true)
    try {
      await firstValueFrom(this.api.resendInvite(member.id))
      this.toastService.showInfo($localize`Invite resent to ${member.email}`)
    } catch (error) {
      this.toastService.showError(this.errorMessage(error, $localize`Unable to resend that invite`))
    } finally {
      this.setActing(member.id, false)
    }
  }

  async revokeInvite(member: OrganizationMember): Promise<void> {
    this.setActing(member.id, true)
    try {
      await firstValueFrom(this.api.revokeInvite(member.id))
      this.toastService.showInfo($localize`Invite for ${member.email} revoked`)
      this.members.update((current) => current.filter((row) => row.id !== member.id))
    } catch (error) {
      this.toastService.showError(this.errorMessage(error, $localize`Unable to revoke that invite`))
    } finally {
      this.setActing(member.id, false)
    }
  }

  isSelf(member: OrganizationMember): boolean {
    return member.id === this.settingsService.currentUser()?.id
  }

  private setMemberActiveState(memberId: number, isActive: boolean): void {
    this.members.update((current) =>
      current.map((row) => (row.id === memberId ? { ...row, is_active: isActive } : row))
    )
  }

  async deactivateTeammate(member: OrganizationMember): Promise<void> {
    this.setActing(member.id, true)
    try {
      await firstValueFrom(this.api.deactivateTeammate(member.id))
      this.toastService.showInfo($localize`${member.username} deactivated`)
      this.setMemberActiveState(member.id, false)
    } catch (error) {
      this.toastService.showError(this.errorMessage(error, $localize`Unable to deactivate that teammate`))
    } finally {
      this.setActing(member.id, false)
    }
  }

  async reactivateTeammate(member: OrganizationMember): Promise<void> {
    this.setActing(member.id, true)
    try {
      await firstValueFrom(this.api.reactivateTeammate(member.id))
      this.toastService.showInfo($localize`${member.username} reactivated`)
      this.setMemberActiveState(member.id, true)
    } catch (error) {
      this.toastService.showError(this.errorMessage(error, $localize`Unable to reactivate that teammate`))
    } finally {
      this.setActing(member.id, false)
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
