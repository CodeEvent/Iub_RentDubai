import { CommonModule } from '@angular/common'
import { Component, inject, OnInit, signal } from '@angular/core'
import {
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms'
import { Router } from '@angular/router'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { debounceTime, distinctUntilChanged } from 'rxjs'
import {
  AddOn,
  NoticeDocument,
  Reason,
  RentshieldApiService,
} from '../services/rentshield-api.service'

const STEPS = ['Parties', 'Property', 'Notice & Reason', 'Review']

@Component({
  selector: 'app-notice-wizard',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, NgxBootstrapIconsModule],
  templateUrl: './notice-wizard.component.html',
  styleUrl: './notice-wizard.component.scss',
})
export class NoticeWizardComponent implements OnInit {
  private fb = inject(FormBuilder)
  private api = inject(RentshieldApiService)
  private router = inject(Router)

  steps = STEPS
  step = signal(0)
  mobileLang = signal<'en' | 'ar'>('en')

  reasons = signal<Record<string, Reason>>({})
  statutoryKeys = ['sale', 'personal', 'demolition', 'renovation']
  breachKeys = ['nonpayment', 'sublease']

  basePriceAed = signal(95)
  addOns = signal<Record<string, AddOn>>({})

  preview = signal<NoticeDocument | null>(null)
  noticePeriodDays = signal(365)
  totalPriceAed = signal(95)
  previewLoading = signal(false)

  saving = signal(false)
  saveError = signal<string | null>(null)
  savedId = signal<number | null>(null)
  paid = signal(false)

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

  // `FormGroup.valid`/`.value` are plain getters, not Angular Signals —
  // computed() would only read them once and never re-evaluate. These
  // are real signals kept in sync via statusChanges/valueChanges below.
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

    this.form.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)))
      .subscribe(() => this.refreshPreview())
    this.refreshPreview()
  }

  refreshPreview(): void {
    const v = this.form.value
    if (!v.reason) {
      this.preview.set(null)
      return
    }
    this.previewLoading.set(true)
    this.api.previewNotice(v).subscribe({
      next: (res) => {
        this.preview.set(res.document)
        this.noticePeriodDays.set(res.notice_period_days)
        this.totalPriceAed.set(res.total_price_aed)
        this.previewLoading.set(false)
      },
      error: () => this.previewLoading.set(false),
    })
  }

  goStep(delta: number): void {
    const next = this.step() + delta
    if (next < 0 || next > this.steps.length - 1) return
    this.step.set(next)
  }

  selectReason(key: string): void {
    this.form.patchValue({ reason: key })
  }

  reviewValue(v: string | null | undefined): string {
    return v && v.trim() ? v : 'Not provided'
  }

  save(): void {
    if (!this.form.valid) return
    if (this.needsLandlordEmail()) {
      this.saveError.set(
        'A landlord email is required when Notarization is selected.'
      )
      return
    }
    this.saving.set(true)
    this.saveError.set(null)
    this.api.createNotice(this.form.value).subscribe({
      next: (notice) => {
        this.saving.set(false)
        this.savedId.set(notice.id)
        this.paid.set(true)
        if (notice.add_notarization) {
          this.api.notarize(notice.id).subscribe()
        }
      },
      error: (err) => {
        this.saving.set(false)
        this.saveError.set(
          err?.error?.error || err?.message || 'Save failed'
        )
      },
    })
  }

  viewSaved(): void {
    // No per-notice detail route exists yet — route to the saved-notices
    // list, which shows every notice including the one just created.
    if (this.savedId()) this.router.navigate(['/rentshield/notices'])
  }
}
