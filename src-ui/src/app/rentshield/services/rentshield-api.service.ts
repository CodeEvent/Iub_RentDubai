import { HttpClient } from '@angular/common/http'
import { Injectable, inject } from '@angular/core'
import { Observable, forkJoin, interval, of } from 'rxjs'
import { filter, map, shareReplay, switchMap, take } from 'rxjs/operators'
import { environment } from 'src/environments/environment'

export interface Reason {
  label: string
  label_ar: string
  warning: string
  clause_en: string
  clause_ar: string
}

export interface AddOn {
  label: string
  description: string
  price_aed: number
}

// A RentShield "notice" is a real paperless-ngx Document -- `id` here
// IS the paperless Document id. There is no separate rentshield
// database table or API: this shape is assembled client-side from a
// stock GET /api/documents/<id>/ response's `custom_fields` array (see
// documentToNotice() below), not returned directly by any endpoint.
export interface Notice {
  id: number
  landlord_name: string
  landlord_email: string | null
  tenant_name: string
  property_type: string
  unit_no: string | null
  building_name: string | null
  plot_number: string | null
  ejari_number: string | null
  notice_date: string
  reason: string
  reason_label: string
  notice_period_days: number
  add_notarization: boolean
  add_ai_review: boolean
  add_real_notarization: boolean
  total_price_aed: number
  document_id: number | null
  esign_provider: string | null
  esign_status: string | null
  esign_signing_url: string | null
  esign_signed_document_url: string | null
  notary_status: string | null
  notary_reference_no: string | null
  created_at: string
}

export interface LegalSkillSummary {
  id: string
  title: string
  jurisdiction: string
  practice_area: string
}

export interface LegalSkill extends LegalSkillSummary {
  body: string
  disclaimer: string
  status: string
}

export interface CitationGraphEdge {
  from: string
  to: string
  relation: 'contains' | 'has' | 'satisfies' | 'violates'
  note?: string
}

export interface CitationGraphNode {
  id: string
  type: string
  label: string
  category?: string
}

export interface CitationGraph {
  nodes: CitationGraphNode[]
  edges: CitationGraphEdge[]
  ejari_number: string | null
  has_violation: boolean
  violation_count: number
}

export interface DocumentAnalysisResult {
  source: string
  markdown?: string
  text: string
  num_pages?: number
  tables?: unknown[]
  citation_graph: CitationGraph
}

// What the property owner declares on the web before scanning the QR
// (identity-verification.component.ts) -- field names match the
// `declared_*` keys pairing_views.py's pair_start_view validates and
// stores. Passport needs the BAC key components (document number, DOB,
// expiry); CIE needs its PACE key (the CAN, never the card's longer
// printed serial number) plus its own document number.
export interface DeclaredDocument {
  declared_document_type: 'passport' | 'cie'
  declared_document_number: string
  declared_date_of_birth?: string
  declared_expiry_date?: string
  declared_can?: string
}

// Mirrors IdentityVerificationCall.to_dict() (documents/
// rentshield_identity/models.py) -- one shape shared by the property
// owner's own status endpoint and the Notary's review list.
export interface VideoCall {
  id: number
  status: string
  scheduled_at: string
  room_name: string
  join_open: boolean
  notary_call_notes: string
  recording_url: string | null
  jitsi_base_url: string
}

// Optional filters for getIdentityVerificationAdminList/buildAdminExportUrl
// -- see admin_views.py's _filtered_records.
export interface AdminListFilters {
  q?: string
  filterStatus?: string
  dateFrom?: string
  dateTo?: string
}

// Mirrors IdentityVerificationAuditLog.to_dict().
export interface AuditLogEntry {
  action: string
  action_label: string
  actor: string | null
  notes: string
  created_at: string
}

export interface AdminVerificationRecord {
  id: number
  username: string
  email: string
  status: string
  provider: string
  verification_id: string
  passport_photo_url: string | null
  selfie_photo_url: string | null
  video_url: string | null
  chip_photo_url: string | null
  additional_id_type: string
  additional_id_type_label: string
  additional_id_photo_front_url: string | null
  additional_id_photo_back_url: string | null
  chip_selfie_match_score: number | null
  latitude: number | null
  longitude: number | null
  location_accuracy_m: number | null
  declared_document_type: string
  declared_document_number: string
  declared_date_of_birth: string
  card_ocr_full_name: string
  card_ocr_date_of_birth: string
  card_ocr_document_number: string
  chip_full_name: string
  chip_date_of_birth: string
  chip_document_number: string
  identity_mismatch_notes: string
  automated_result: string
  notary_reviewed_by: string | null
  notary_reviewed_at: string | null
  notary_notes: string
  ai_prescreen_summary: string
  video_call: VideoCall | null
  claimed_by: string | null
  claimed_at: string | null
  claim_conflict: boolean
  audit_log: AuditLogEntry[]
  created_at: string
  updated_at: string
}

// My Profile > Security tab (2026-09-22) -- mirrors ZITADEL's own
// Passkey message shape (zitadel/user/v2/user.proto), confirmed live
// against the running instance, not guessed.
export interface Passkey {
  id: string
  name: string
  state: string
}

// Mirrors documents/rentshield_views.py's organization_status_view /
// organization_dashboard_view response shapes exactly -- see that
// file's own docstrings for why status_breakdown is a count per real
// pipeline-stage tag rather than an invented linear status enum.
export interface OrganizationStatus {
  in_organization: boolean
  organization_name: string | null
}

export interface OrganizationStatusCount {
  tags__name: string
  count: number
}

export interface OrganizationDeadline {
  document_id: number
  title: string
  deadline: string
  days_remaining: number
}

export interface OrganizationActivity {
  id: number
  title: string
  modified: string
  owner__username: string
}

export interface OrganizationDashboard {
  organization: { id: number; name: string }
  active_notices_count: number
  status_breakdown: OrganizationStatusCount[]
  upcoming_deadlines: OrganizationDeadline[]
  recent_activity: OrganizationActivity[]
}

const RENTSHIELD_TAG_NAME = 'RentShield Notice'

interface PaperlessCustomFieldDef {
  id: number
  name: string
}

interface PaperlessDocumentCustomField {
  field: number
  value: unknown
}

interface PaperlessDocument {
  id: number
  created: string
  custom_fields: PaperlessDocumentCustomField[]
}

interface PaperlessTaskRow {
  status: string
  related_document_ids: number[]
}

// Short field keys used throughout this service map 1:1 onto the
// CustomField display names created by the backend's bootstrap data
// migration (documents/migrations/0026_rentshield_custom_fields.py) --
// see documents/rentshield/custom_fields.py FIELD_KEYS for the
// authoritative Python-side list this mirrors.
const FIELD_KEYS: Record<string, string> = {
  landlord_name: 'RentShield: Landlord Name',
  landlord_email: 'RentShield: Landlord Email',
  tenant_name: 'RentShield: Tenant Name',
  property_type: 'RentShield: Property Type',
  unit_no: 'RentShield: Unit No.',
  building_name: 'RentShield: Building / Community',
  plot_number: 'RentShield: Plot No.',
  ejari_number: 'RentShield: Ejari No.',
  notice_date: 'RentShield: Notice Date',
  reason: 'RentShield: Reason',
  notice_period_days: 'RentShield: Notice Period (Days)',
  add_notarization: 'RentShield: Notarization Add-on',
  add_ai_review: 'RentShield: AI Review Add-on',
  total_price_aed: 'RentShield: Total Price (AED)',
  esign_provider: 'RentShield: E-Sign Provider',
  esign_external_id: 'RentShield: E-Sign External ID',
  esign_signing_url: 'RentShield: E-Sign Signing URL',
  esign_status: 'RentShield: E-Sign Status',
  esign_signed_document_url: 'RentShield: E-Sign Signed Document URL',
  add_real_notarization: 'RentShield: Real Notarization Add-on',
  notary_status: 'RentShield: Notary Public Status',
  notary_reference_no: 'RentShield: Notary Reference No.',
}

@Injectable({ providedIn: 'root' })
export class RentshieldApiService {
  private http = inject(HttpClient)
  // paperless-ngx's own API root -- every call below hits a stock
  // paperless-ngx endpoint (documents, tags, custom_fields, tasks) or a
  // notice-specific endpoint mounted directly under documents/ in
  // paperless/urls.py (not a separate rentshield API namespace).
  private base = environment.apiBaseUrl

  // Looks up a tag's live id by name -- paperless-ngx has no "get tag by
  // name" endpoint, just filtering, so this is the same one-line lookup
  // every tag-by-name need here shares. shareReplay(1) so it's resolved
  // once per app session, not re-fetched on every subscribe.
  private tagId(name: string): Observable<number | null> {
    return this.http
      .get<{ results: { id: number; name: string }[] }>(
        `${this.base}tags/?name__iexact=${encodeURIComponent(name)}`
      )
      .pipe(
        map((res) => res.results[0]?.id ?? null),
        shareReplay(1)
      )
  }

  // Resolved once per app session and cached: the "RentShield Notice"
  // tag id (documents carrying it are RentShield notices), the
  // "Awaiting Notary Public" tag id (the Real Notary Public fulfillment
  // queue -- see the Notary Guide page), and the CustomField
  // id <-> short-key maps used to build/read the custom_fields payload
  // on a Document.
  private rentshieldTagId$ = this.tagId(RENTSHIELD_TAG_NAME)
  private awaitingNotaryTagId$ = this.tagId('Awaiting Notary Public')

  private customFieldIdToKey$ = this.http
    .get<{ results: PaperlessCustomFieldDef[] }>(`${this.base}custom_fields/?page_size=100`)
    .pipe(
      map((res) => {
        const nameToKey: Record<string, string> = {}
        for (const [key, name] of Object.entries(FIELD_KEYS)) nameToKey[name] = key
        const idToKey: Record<number, string> = {}
        for (const field of res.results) {
          const key = nameToKey[field.name]
          if (key) idToKey[field.id] = key
        }
        return idToKey
      }),
      shareReplay(1)
    )

  private documentToNotice(
    doc: PaperlessDocument,
    idToKey: Record<number, string>,
    reasons: Record<string, Reason>
  ): Notice {
    const f: Record<string, unknown> = {}
    for (const cf of doc.custom_fields ?? []) {
      const key = idToKey[cf.field]
      if (key) f[key] = cf.value
    }
    const reason = (f['reason'] as string) ?? ''
    const reasonMeta = reasons[reason]
    return {
      id: doc.id,
      landlord_name: (f['landlord_name'] as string) ?? '',
      landlord_email: (f['landlord_email'] as string) ?? null,
      tenant_name: (f['tenant_name'] as string) ?? '',
      property_type: (f['property_type'] as string) ?? 'Apartment',
      unit_no: (f['unit_no'] as string) ?? null,
      building_name: (f['building_name'] as string) ?? null,
      plot_number: (f['plot_number'] as string) ?? null,
      ejari_number: (f['ejari_number'] as string) ?? null,
      notice_date: (f['notice_date'] as string) ?? '',
      reason,
      reason_label: reasonMeta?.label ?? reason,
      notice_period_days: (f['notice_period_days'] as number) ?? 365,
      add_notarization: !!f['add_notarization'],
      add_ai_review: !!f['add_ai_review'],
      add_real_notarization: !!f['add_real_notarization'],
      total_price_aed: (f['total_price_aed'] as number) ?? 0,
      document_id: doc.id,
      esign_provider: (f['esign_provider'] as string) ?? null,
      esign_status: (f['esign_status'] as string) ?? null,
      esign_signing_url: (f['esign_signing_url'] as string) ?? null,
      esign_signed_document_url: (f['esign_signed_document_url'] as string) ?? null,
      notary_status: (f['notary_status'] as string) ?? null,
      notary_reference_no: (f['notary_reference_no'] as string) ?? null,
      created_at: doc.created,
    }
  }

  getReasons(): Observable<{ reasons: Record<string, Reason> }> {
    return this.http.get<{ reasons: Record<string, Reason> }>(`${this.base}documents/notice/reasons/`)
  }

  getPricing(): Observable<{ base_price_aed: number; add_ons: Record<string, AddOn> }> {
    return this.http.get<{ base_price_aed: number; add_ons: Record<string, AddOn> }>(
      `${this.base}documents/notice/pricing/`
    )
  }

  // The Real Notary Public fulfillment queue's tag id -- used to deep-link
  // straight into the filtered document list (see the Notary Guide page),
  // the same way listNotices() above filters by the RentShield tag.
  getAwaitingNotaryTagId(): Observable<number | null> {
    return this.awaitingNotaryTagId$
  }

  // Lists every RentShield notice by querying paperless-ngx's own stock
  // document list, filtered to the "RentShield Notice" tag -- there is
  // no dedicated notices-list endpoint.
  listNotices(): Observable<Notice[]> {
    return forkJoin({
      tagId: this.rentshieldTagId$,
      idToKey: this.customFieldIdToKey$,
      reasons: this.getReasons(),
    }).pipe(
      switchMap(({ tagId, idToKey, reasons }) => {
        if (tagId === null) return of([] as Notice[])
        return this.http
          .get<{ results: PaperlessDocument[] }>(
            `${this.base}documents/?tags__id__in=${tagId}&ordering=-created&page_size=100`
          )
          .pipe(
            map((res) => res.results.map((doc) => this.documentToNotice(doc, idToKey, reasons.reasons)))
          )
      })
    )
  }

  getNotice(id: number): Observable<Notice> {
    return forkJoin({
      doc: this.http.get<PaperlessDocument>(`${this.base}documents/${id}/`),
      idToKey: this.customFieldIdToKey$,
      reasons: this.getReasons(),
    }).pipe(map(({ doc, idToKey, reasons }) => this.documentToNotice(doc, idToKey, reasons.reasons)))
  }

  // Renders the bilingual PDF and dispatches it into paperless-ngx's own
  // consumption pipeline -- this is genuinely async (real OCR + full-text
  // indexing happen in the Celery worker), so this only returns a task
  // id. Use waitForNotice() to resolve it into a Document id once
  // consumption finishes.
  createNotice(payload: Partial<Notice>): Observable<{ task_id: string }> {
    return this.http.post<{ task_id: string }>(`${this.base}documents/notice/create/`, payload)
  }

  // Polls paperless-ngx's own stock GET /api/tasks/?task_id=... (the
  // same endpoint its own web UI uses for the Tasks page) every 1.2s
  // until the consume_file task started by createNotice() finishes,
  // then resolves with the resulting Document id.
  waitForNotice(taskId: string): Observable<{ status: string; document_id: number | null }> {
    return interval(1200).pipe(
      switchMap(() =>
        this.http.get<{ results: PaperlessTaskRow[] }>(`${this.base}tasks/?task_id=${taskId}`)
      ),
      map((res) => res.results[0]),
      filter((row) => !!row && (row.status === 'success' || row.status === 'failure')),
      take(1),
      map((row) => ({
        status: row.status,
        document_id: row.related_document_ids?.[0] ?? null,
      }))
    )
  }

  // The real, payment-gated path (documents/rentshield_billing/) --
  // notice-form now calls this instead of createNotice() directly. In
  // demo mode (no Stripe key configured server-side) the notice is
  // already generated by the time this resolves, so document_id comes
  // back directly; in real-Stripe mode checkout_url is set instead and
  // the caller must redirect there, with generation happening later via
  // Stripe's webhook once payment actually completes.
  checkout(payload: Partial<Notice>): Observable<{
    order_id: number
    demo: boolean
    checkout_url: string | null
    status: string
    document_id: number | null
  }> {
    return this.http.post<{
      order_id: number
      demo: boolean
      checkout_url: string | null
      status: string
      document_id: number | null
    }>(`${this.base}documents/notice/checkout/`, payload)
  }

  notarize(
    documentId: number
  ): Observable<{ provider: string; status: string; signing_url: string | null }> {
    return this.http.post<{
      provider: string
      status: string
      signing_url: string | null
    }>(`${this.base}documents/notice/${documentId}/notarize/`, {})
  }

  getNotarizeStatus(documentId: number): Observable<{
    provider: string
    status: string
    signed_document_url: string | null
  }> {
    return this.http.get<{
      provider: string
      status: string
      signed_document_url: string | null
    }>(`${this.base}documents/notice/${documentId}/notarize-status/`)
  }

  // Property-owner identity verification (documents/rentshield_identity/,
  // self-hosted Idswyft -- camera capture + liveness + face match, not
  // NFC chip reading, see that app's models.py for why). The capture
  // itself (photo + selfie) happens right inside identity-verification.
  // component.ts, uploaded through the two endpoints below -- the
  // property owner never leaves RentShield's own page or sees Idswyft's
  // branding. A 503 from startIdentityVerification means the feature
  // isn't configured in this environment, not that the request itself
  // failed -- callers should show that message as-is.
  startIdentityVerification(): Observable<{ status: string; step: string }> {
    return this.http.post<{ status: string; step: string }>(
      `${this.base}documents/identity/verify/start/`,
      {}
    )
  }

  getIdentityVerificationStatus(): Observable<{
    status: string | null
    step: string | null
    notary_notes: string
    video_call: VideoCall | null
  }> {
    return this.http.get<{ status: string | null; step: string | null; notary_notes: string; video_call: VideoCall | null }>(
      `${this.base}documents/identity/verify/status/`
    )
  }

  // "Scan to sign in" device pairing (documents/rentshield_identity/
  // pairing_views.py) -- the whole capture flow (NFC chip, selfie,
  // video) only exists in the native app, so the web page's job here is
  // just to get the app authenticated as this same user, via a QR code
  // instead of the property owner typing a password on their phone.
  // `declared` is what the user just typed in the "declare your
  // document" step -- typed on a real keyboard specifically to cut
  // down the CAN/document-number typos that kept happening when this
  // was only ever typed on the app's own small screen; the backend
  // stores it and hands it back to the app on claim so it can pre-fill
  // instead of asking again from scratch (see pairing_views.py).
  startDevicePairing(declared: DeclaredDocument): Observable<{
    code: string
    qr_data_uri: string
    expires_at: string
    apk_url: string | null
  }> {
    return this.http.post<{ code: string; qr_data_uri: string; expires_at: string; apk_url: string | null }>(
      `${this.base}documents/identity/pair/start/`,
      declared
    )
  }

  getDevicePairingStatus(): Observable<{ status: string | null }> {
    return this.http.get<{ status: string | null }>(`${this.base}documents/identity/pair/status/`)
  }

  private appendGeolocation(formData: FormData, position: GeolocationPosition | null): void {
    if (!position) return
    formData.append('latitude', String(position.coords.latitude))
    formData.append('longitude', String(position.coords.longitude))
    formData.append('location_accuracy_m', String(position.coords.accuracy))
  }

  uploadIdentityFrontDocument(
    file: File,
    position: GeolocationPosition | null = null
  ): Observable<{ step: string; status: string }> {
    const formData = new FormData()
    formData.append('document', file)
    this.appendGeolocation(formData, position)
    return this.http.post<{ step: string; status: string }>(
      `${this.base}documents/identity/verify/front-document/`,
      formData
    )
  }

  uploadIdentityLiveCapture(
    file: File,
    position: GeolocationPosition | null = null
  ): Observable<{ step: string; status: string }> {
    const formData = new FormData()
    formData.append('selfie', file)
    this.appendGeolocation(formData, position)
    return this.http.post<{ step: string; status: string }>(
      `${this.base}documents/identity/verify/live-capture/`,
      formData
    )
  }

  // Lets the frontend show the "Identity Verification Admin" nav link
  // to a Notary Public account too, not just is_staff admins -- see
  // admin_views.py's notary_status_view docstring for why this exists
  // (a Notary account with no is_staff has real backend access to the
  // review page but no other way to know that / find the nav link).
  getNotaryStatus(): Observable<{ is_notary_public: boolean }> {
    return this.http.get<{ is_notary_public: boolean }>(`${this.base}documents/identity/verify/notary-status/`)
  }

  // Admin-only review list (documents/rentshield_identity/admin_views.py)
  // -- defaults to only the records actually awaiting a Notary's
  // review; pass includeAll to see the full history instead. `filters`
  // (2026-09-14) only really matters once that history view has more
  // than a handful of rows -- q (username/email substring),
  // filterStatus (exact status), dateFrom/dateTo (YYYY-MM-DD, matches
  // <input type="date">'s own value format).
  getIdentityVerificationAdminList(
    includeAll = false,
    filters: AdminListFilters = {}
  ): Observable<{ results: AdminVerificationRecord[] }> {
    return this.http.get<{ results: AdminVerificationRecord[] }>(
      `${this.base}documents/identity/verify/admin/list/`,
      { params: this.adminListParams(includeAll, filters) }
    )
  }

  // The CSV export (admin_export_verifications_view) takes the exact
  // same filters as the list above -- "export whatever I'm currently
  // looking at" -- so it shares the same param-building instead of a
  // second copy of it. Returns a plain URL (not an Observable): the
  // browser's own session cookie handles auth for a normal navigation/
  // download, same as any other paperless-ngx file download.
  buildAdminExportUrl(includeAll: boolean, filters: AdminListFilters = {}): string {
    const params = this.adminListParams(includeAll, filters)
    const query = new URLSearchParams(params).toString()
    return `${this.base}documents/identity/verify/admin/export/${query ? '?' + query : ''}`
  }

  private adminListParams(includeAll: boolean, filters: AdminListFilters): Record<string, string> {
    const params: Record<string, string> = {}
    if (includeAll) params['status'] = 'all'
    if (filters.q) params['q'] = filters.q
    if (filters.filterStatus) params['filter_status'] = filters.filterStatus
    if (filters.dateFrom) params['date_from'] = filters.dateFrom
    if (filters.dateTo) params['date_to'] = filters.dateTo
    return params
  }

  // Advisory lock (documents/rentshield_identity/views.py's
  // claim_verification_view/release_verification_view) -- prevents two
  // Notaries acting on the same record at once with no warning.
  claimVerification(id: number): Observable<{ claimed_by: string | null }> {
    return this.http.post<{ claimed_by: string | null }>(`${this.base}documents/identity/verify/notary/${id}/claim/`, {})
  }

  releaseVerification(id: number): Observable<{ claimed_by: string | null }> {
    return this.http.post<{ claimed_by: string | null }>(`${this.base}documents/identity/verify/notary/${id}/release/`, {})
  }

  // Notary Public review actions (documents/rentshield_identity/views.py's
  // notary_confirm_view/notary_reject_view) -- the only path that ever
  // sets a verification to "verified"; see IdentityVerification's own
  // docstring on why the automated result alone no longer does. `edits`
  // carries any OCR/chip field corrections the reviewer made on the
  // page, keyed as `edit_<field>` (see views.py's _NOTARY_EDITABLE_FIELDS).
  confirmIdentityVerification(
    id: number,
    notes: string,
    edits: Record<string, string> = {}
  ): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${this.base}documents/identity/verify/notary/${id}/confirm/`,
      { notes, ...edits }
    )
  }

  rejectIdentityVerification(
    id: number,
    notes: string,
    edits: Record<string, string> = {}
  ): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${this.base}documents/identity/verify/notary/${id}/reject/`,
      { notes, ...edits }
    )
  }

  // A third outcome alongside confirm/reject (views.py's
  // notary_request_more_info_view) -- not a final decision like reject:
  // sends the record back to the user's own pipeline without deleting
  // any of their evidence. `notes` is required by the backend (unlike
  // confirm/reject) since without it the user has no idea what to redo.
  requestMoreInfoOnIdentityVerification(
    id: number,
    notes: string,
    edits: Record<string, string> = {}
  ): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${this.base}documents/identity/verify/notary/${id}/request-more-info/`,
      { notes, ...edits }
    )
  }

  // Available to an Admin or a Notary Public (documents/
  // rentshield_identity/views.py's admin_reset_verification_view) --
  // wipes a user's whole verification back to a clean slate (every
  // uploaded file, every OCR/chip/declared field, any Notary decision)
  // so they can redo the pipeline from scratch. For a record too broken
  // to send back with requestMoreInfoOnIdentityVerification above.
  resetIdentityVerification(id: number): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}documents/identity/verify/admin/${id}/reset/`, {})
  }

  // Available to an Admin or a Notary Public (documents/
  // rentshield_identity/views.py's admin_delete_verification_view) --
  // permanently removes the whole record, not just its evidence like
  // resetIdentityVerification above. No status gate on the backend --
  // pending, awaiting review, verified, failed, any of them can be
  // deleted. For a record that shouldn't be in the list at all (spam,
  // a duplicate/wrong account, test data), not a real one to redo.
  deleteIdentityVerification(id: number): Observable<{ deleted: boolean }> {
    return this.http.post<{ deleted: boolean }>(`${this.base}documents/identity/verify/admin/${id}/delete/`, {})
  }

  // Live video call scheduling (documents/rentshield_identity/views.py's
  // schedule_video_call_view et al.) -- the one synchronous moment in
  // an otherwise fully async pipeline. `scheduledAt` is an ISO 8601
  // string (native <input type="datetime-local"> already produces one).
  scheduleVideoCall(verificationId: number, scheduledAt: string): Observable<{ call: VideoCall }> {
    return this.http.post<{ call: VideoCall }>(
      `${this.base}documents/identity/verify/notary/${verificationId}/schedule-call/`,
      { scheduled_at: scheduledAt }
    )
  }

  confirmVideoCall(callId: number): Observable<{ call: VideoCall }> {
    return this.http.post<{ call: VideoCall }>(`${this.base}documents/identity/verify/call/${callId}/confirm/`, {})
  }

  requestVideoCallReschedule(callId: number, reason: string): Observable<{ call: VideoCall }> {
    return this.http.post<{ call: VideoCall }>(
      `${this.base}documents/identity/verify/call/${callId}/request-reschedule/`,
      { reason }
    )
  }

  completeVideoCall(
    verificationId: number,
    callId: number,
    notes: string,
    noShow: boolean
  ): Observable<{ call: VideoCall }> {
    return this.http.post<{ call: VideoCall }>(
      `${this.base}documents/identity/verify/notary/${verificationId}/calls/${callId}/complete/`,
      { notes, no_show: noShow }
    )
  }

  listLegalSkills(): Observable<{ skills: LegalSkillSummary[] }> {
    return this.http.get<{ skills: LegalSkillSummary[] }>(`${this.base}documents/notice/legal-skills/`)
  }

  getLegalSkill(id: string): Observable<{ skill: LegalSkill }> {
    return this.http.get<{ skill: LegalSkill }>(`${this.base}documents/notice/legal-skills/${id}/`)
  }

  checkServiceMethod(method: string): Observable<{
    method: string
    is_valid_under_article_25_3: boolean
    note: string
  }> {
    return this.http.post<{
      method: string
      is_valid_under_article_25_3: boolean
      note: string
    }>(`${this.base}documents/notice/check-service-method/`, { method })
  }

  analyzeDocument(file: File, useDeepseekOcr = false): Observable<DocumentAnalysisResult> {
    const formData = new FormData()
    formData.append('file', file)
    if (useDeepseekOcr) formData.append('use_deepseek_ocr', 'true')
    return this.http.post<DocumentAnalysisResult>(`${this.base}documents/notice/analyze/`, formData)
  }

  // My Profile > Security tab (2026-09-22) -- replaces the deleted
  // AutheliaSecurityService. No rename (ZITADEL's passkey API has none)
  // and no elevation/step-up gate (see rentshield_passkeys_view's own
  // comment in rentshield_views.py for why that's not a regression).
  listPasskeys(): Observable<Passkey[]> {
    return this.http.get<Passkey[]>(`${this.base}documents/security/passkeys/`)
  }

  // Returns a redirect_url on zitadel.rentshield.local -- the WebAuthn
  // ceremony can't run on this origin at all (see zitadel/nginx/
  // rentshield-bridge/index.html's own header comment on the RP-id
  // constraint). Caller navigates there; returnTo is where the bridge
  // page sends the browser back once the ceremony completes.
  startAddPasskey(description: string, returnTo: string): Observable<{ redirect_url: string }> {
    return this.http.post<{ redirect_url: string }>(`${this.base}documents/security/passkeys/add/`, {
      description,
      return_to: returnTo,
    })
  }

  deletePasskey(passkeyId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}documents/security/passkeys/${passkeyId}/`)
  }

  // Agency Dashboard (2026-09-22) -- getOrganizationStatus() is the
  // cheap boolean call app-frame.component.ts's ngOnInit uses to decide
  // nav-link visibility (same pattern as its existing getNotaryStatus()
  // call); getOrganizationDashboard() is the heavier aggregate call the
  // dashboard page itself makes once actually navigated to, not on
  // every page load.
  getOrganizationStatus(): Observable<OrganizationStatus> {
    return this.http.get<OrganizationStatus>(`${this.base}documents/organization/status/`)
  }

  getOrganizationDashboard(): Observable<OrganizationDashboard> {
    return this.http.get<OrganizationDashboard>(`${this.base}documents/organization/dashboard/`)
  }

  // Backend creates the account and emails the invite link immediately
  // (documents/rentshield_views.py's rentshield_invite_view's own
  // comment on why) -- this call either succeeds (201, no body) or
  // fails with a plain { error: string } the caller shows directly.
  inviteTeammate(email: string): Observable<void> {
    return this.http.post<void>(`${this.base}documents/organization/invite/`, { email })
  }
}
