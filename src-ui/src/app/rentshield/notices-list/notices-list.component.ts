import { CommonModule } from '@angular/common'
import { Component, computed, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { TourNgBootstrap } from 'ngx-ui-tour-ng-bootstrap'
import { ToastService } from 'src/app/services/toast.service'
import {
  Notice,
  RentshieldApiService,
} from '../services/rentshield-api.service'

@Component({
  selector: 'app-notices-list',
  standalone: true,
  imports: [CommonModule, RouterModule, NgxBootstrapIconsModule, TourNgBootstrap],
  templateUrl: './notices-list.component.html',
  styleUrl: './notices-list.component.scss',
})
export class NoticesListComponent {
  private api = inject(RentshieldApiService)
  private toastService = inject(ToastService)

  notices = signal<Notice[]>([])
  loading = signal(true)
  private readonly generatingPacketIds = signal<Set<number>>(new Set())

  total = computed(() => this.notices().length)
  statutory = computed(
    () => this.notices().filter((n) => n.notice_period_days === 365).length
  )
  breach = computed(
    () => this.notices().filter((n) => n.notice_period_days === 30).length
  )
  aiReviewed = computed(
    () => this.notices().filter((n) => n.add_ai_review).length
  )

  constructor() {
    this.api.listNotices().subscribe({
      next: (notices) => {
        this.notices.set(notices)
        this.loading.set(false)
      },
      error: () => this.loading.set(false),
    })
  }

  isGeneratingPacket(documentId: number): boolean {
    return this.generatingPacketIds().has(documentId)
  }

  generateRdscPacket(notice: Notice): void {
    if (!notice.document_id) return
    const documentId = notice.document_id
    this.generatingPacketIds.update((current) => new Set(current).add(documentId))
    this.api.generateRdscPacket(documentId).subscribe({
      next: () => {
        this.toastService.showInfo(
          $localize`Filing packet queued -- it'll appear in your documents shortly.`
        )
        this.generatingPacketIds.update((current) => {
          const next = new Set(current)
          next.delete(documentId)
          return next
        })
      },
      error: (err) => {
        this.toastService.showError(
          err?.error?.error || $localize`Could not generate a filing packet -- try again.`
        )
        this.generatingPacketIds.update((current) => {
          const next = new Set(current)
          next.delete(documentId)
          return next
        })
      },
    })
  }
}
