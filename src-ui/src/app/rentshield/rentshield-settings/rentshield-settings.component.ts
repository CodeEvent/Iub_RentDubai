import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { AddOn, RentshieldApiService } from '../services/rentshield-api.service'

@Component({
  selector: 'app-rentshield-settings',
  standalone: true,
  imports: [CommonModule, NgxBootstrapIconsModule],
  templateUrl: './rentshield-settings.component.html',
  styleUrl: './rentshield-settings.component.scss',
})
export class RentshieldSettingsComponent {
  private api = inject(RentshieldApiService)

  apiOk = signal<boolean | null>(null)
  basePriceAed = signal(0)
  addOns = signal<Record<string, AddOn>>({})

  constructor() {
    this.api.getReasons().subscribe({
      next: () => this.apiOk.set(true),
      error: () => this.apiOk.set(false),
    })
    this.api.getPricing().subscribe((res) => {
      this.basePriceAed.set(res.base_price_aed)
      this.addOns.set(res.add_ons)
    })
  }
}
