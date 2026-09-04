import { CommonModule } from '@angular/common'
import { Component, OnInit, inject, signal } from '@angular/core'
import {
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms'
import { RouterModule } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { TourNgBootstrap } from 'ngx-ui-tour-ng-bootstrap'
import {
  AddOn,
  Reason,
  RentshieldApiService,
} from '../services/rentshield-api.service'

@Component({
  selector: 'app-notice-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule, NgxBootstrapIconsModule, TourNgBootstrap],
  templateUrl: './notice-form.component.html',
  styleUrl: './notice-form.component.scss',
})
export class NoticeFormComponent implements OnInit {
  private fb = inject(FormBuilder)
  private api = inject(RentshieldApiService)

  reasons = signal<Record<string, Reason>>({})
  statutoryKeys = ['sale', 'personal', 'demolition', 'renovation']
  breachKeys = ['nonpayment', 'sublease']

  basePriceAed = signal(95)
  addOns = signal<Record<string, AddOn>>({})

  saving = signal(false)
  saveError = signal<string | null>(null)
  savedId = signal<number | null>(null)

  form: FormGroup = this.fb.group({
    landlord_name: ['', Validators.required],
    landlord_email: [''],
    tenant_name: ['', Validators.required],
    property_type: ['Apartment'],
    unit_no: [''],
    building_name: [''],
    plot_number: [''],
    ejari_number: [''],
    notice_date: [new Date().toISOString().slice(0, 10), Validators.required],
    reason: ['', Validators.required],
    add_notarization: [false],
    add_ai_review: [false],
  })

  // FormGroup.valid/.value are plain getters, not Angular Signals —
  // computed() would only read them once and never re-evaluate. These
  // are real signals kept in sync via statusChanges/valueChanges.
  isReady = signal(false)
  needsLandlordEmail = signal(false)

  ngOnInit(): void {
    this.api.getReasons().subscribe((res) => this.reasons.set(res.reasons))
    this.api.getPricing().subscribe((res) => {
      this.basePriceAed.set(res.base_price_aed)
      this.addOns.set(res.add_ons)
    })

    this.form.statusChanges.subscribe(() => this.isReady.set(this.form.valid))
    this.isReady.set(this.form.valid)

    this.form.valueChanges.subscribe((v) => {
      this.needsLandlordEmail.set(!!v.add_notarization && !v.landlord_email)
    })
  }

  totalPriceAed(): number {
    const v = this.form.value
    let total = this.basePriceAed()
    if (v.add_notarization) total += this.addOns()['notarization']?.price_aed ?? 0
    if (v.add_ai_review) total += this.addOns()['ai_review']?.price_aed ?? 0
    return total
  }

  selectReason(key: string): void {
    this.form.patchValue({ reason: key })
  }

  generate(): void {
    if (!this.form.valid) return
    if (this.needsLandlordEmail()) {
      this.saveError.set('A landlord email is required when Notarization is selected.')
      return
    }
    this.saving.set(true)
    this.saveError.set(null)
    const addNotarization = !!this.form.value.add_notarization

    // Renders a real PDF and dispatches it into paperless-ngx's own async
    // consumption pipeline — createNotice() only returns a task id;
    // waitForNotice() polls paperless-ngx's stock task-status endpoint
    // until it resolves into the created Document's id.
    this.api.createNotice(this.form.value).subscribe({
      next: ({ task_id }) => {
        this.api.waitForNotice(task_id).subscribe({
          next: ({ status, document_id }) => {
            this.saving.set(false)
            if (status !== 'success' || !document_id) {
              this.saveError.set('Notice generation failed — check the server logs and try again.')
              return
            }
            this.savedId.set(document_id)
            if (addNotarization) {
              this.api.notarize(document_id).subscribe()
            }
          },
          error: (err) => {
            this.saving.set(false)
            this.saveError.set(err?.error?.error || err?.message || 'Generation failed')
          },
        })
      },
      error: (err) => {
        this.saving.set(false)
        this.saveError.set(err?.error?.error || err?.message || 'Generation failed')
      },
    })
  }

  generateAnother(): void {
    this.savedId.set(null)
    this.saveError.set(null)
    this.form.reset({
      property_type: 'Apartment',
      notice_date: new Date().toISOString().slice(0, 10),
      add_notarization: false,
      add_ai_review: false,
    })
  }
}
