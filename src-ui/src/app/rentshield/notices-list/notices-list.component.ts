import { CommonModule } from '@angular/common'
import { Component, computed, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import {
  Notice,
  RentshieldApiService,
} from '../services/rentshield-api.service'

@Component({
  selector: 'app-notices-list',
  standalone: true,
  imports: [CommonModule, RouterModule, NgxBootstrapIconsModule],
  templateUrl: './notices-list.component.html',
  styleUrl: './notices-list.component.scss',
})
export class NoticesListComponent {
  private api = inject(RentshieldApiService)

  notices = signal<Notice[]>([])
  loading = signal(true)

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
}
