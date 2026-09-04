import { HttpClient } from '@angular/common/http'
import { Injectable, inject } from '@angular/core'
import { Observable, forkJoin, interval, of } from 'rxjs'
import { filter, map, shareReplay, switchMap, take } from 'rxjs/operators'
import { environment } from 'src/environments/environment'

export interface NoticeSide {
  kicker: string
  title: string
  subtitle: string
  date_label: string
  date_value: string
  deadline_label: string
  deadline_value: string
  to: string
  ejari_line: string
  property_line: string
  from: string
  paragraphs: string[]
  reason_label: string
  reason_text: string
  closing: string
  footer: string
  landlord_name: string
  sign_date: string
}

export interface NoticeDocument {
  type: 'statutory' | 'breach'
  days: number
  en: NoticeSide
  ar: NoticeSide
}

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
  total_price_aed: number
  document_id: number | null
  esign_provider: string | null
  esign_status: string | null
  esign_signing_url: string | null
  esign_signed_document_url: string | null
  created_at: string
  document?: NoticeDocument
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
}

@Injectable({ providedIn: 'root' })
export class RentshieldApiService {
  private http = inject(HttpClient)
  // paperless-ngx's own API root -- every call below hits a stock
  // paperless-ngx endpoint (documents, tags, custom_fields, tasks) or a
  // notice-specific endpoint mounted directly under documents/ in
  // paperless/urls.py (not a separate rentshield API namespace).
  private base = environment.apiBaseUrl

  // Resolved once per app session and cached: the "RentShield Notice"
  // tag id (documents carrying it are RentShield notices) and the
  // CustomField id <-> short-key maps used to build/read the
  // custom_fields payload on a Document.
  private rentshieldTagId$ = this.http
    .get<{ results: { id: number; name: string }[] }>(
      `${this.base}tags/?name__iexact=${encodeURIComponent(RENTSHIELD_TAG_NAME)}`
    )
    .pipe(
      map((res) => res.results[0]?.id ?? null),
      shareReplay(1)
    )

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
      total_price_aed: (f['total_price_aed'] as number) ?? 0,
      document_id: doc.id,
      esign_provider: (f['esign_provider'] as string) ?? null,
      esign_status: (f['esign_status'] as string) ?? null,
      esign_signing_url: (f['esign_signing_url'] as string) ?? null,
      esign_signed_document_url: (f['esign_signed_document_url'] as string) ?? null,
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

  previewNotice(payload: Partial<Notice>): Observable<{
    document: NoticeDocument
    notice_period_days: number
    total_price_aed: number
  }> {
    return this.http.post<{
      document: NoticeDocument
      notice_period_days: number
      total_price_aed: number
    }>(`${this.base}documents/notice/preview/`, payload)
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
}
