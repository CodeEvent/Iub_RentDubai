import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { RouterModule } from '@angular/router'
import { NgbPopoverModule } from '@ng-bootstrap/ng-bootstrap'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { TourNgBootstrap } from 'ngx-ui-tour-ng-bootstrap'
import { RentshieldApiService } from '../services/rentshield-api.service'

// Reference/walkthrough page for the Real Notary Public add-on's human
// fulfiller (see documents/rentshield/custom_fields.py's comment above
// AWAITING_NOTARY_PUBLIC_TAG_NAME and the README's dated section) --
// this page IS the guidance (always-visible step cards, same as
// legal-skills being a persistent reference), and app.component.ts's
// tour additionally walks through these same cards on tourAnchor
// anchors for an interactive first-time walkthrough. There is
// deliberately no bespoke completion UI here or anywhere else in this
// flow -- every actual action she takes happens in paperless-ngx's own
// native document editor; this page only explains that and deep-links
// into it.
@Component({
  selector: 'app-notary-guide',
  standalone: true,
  imports: [CommonModule, RouterModule, NgbPopoverModule, NgxBootstrapIconsModule, TourNgBootstrap],
  templateUrl: './notary-guide.component.html',
  styleUrl: './notary-guide.component.scss',
})
export class NotaryGuideComponent {
  private api = inject(RentshieldApiService)

  awaitingNotaryTagId = signal<number | null>(null)

  constructor() {
    this.api.getAwaitingNotaryTagId().subscribe((id) => this.awaitingNotaryTagId.set(id))
  }
}
