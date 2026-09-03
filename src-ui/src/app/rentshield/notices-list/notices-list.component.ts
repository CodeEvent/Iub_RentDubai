import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
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
