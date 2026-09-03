import { HttpClient } from '@angular/common/http'
import { Injectable, inject } from '@angular/core'
import { Observable } from 'rxjs'
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
  consume_task_id: string | null
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

@Injectable({ providedIn: 'root' })
export class RentshieldApiService {
  private http = inject(HttpClient)
  private base = `${environment.apiBaseUrl}rentshield/`

  getReasons(): Observable<{ reasons: Record<string, Reason> }> {
    return this.http.get<{ reasons: Record<string, Reason> }>(
      `${this.base}reasons/`
    )
  }

  getPricing(): Observable<{ base_price_aed: number; add_ons: Record<string, AddOn> }> {
    return this.http.get<{ base_price_aed: number; add_ons: Record<string, AddOn> }>(
      `${this.base}pricing/`
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
    }>(`${this.base}preview-notice/`, payload)
  }

  listNotices(): Observable<Notice[]> {
    return this.http.get<Notice[]>(`${this.base}notices/`)
  }

  getNotice(id: number): Observable<Notice> {
    return this.http.get<Notice>(`${this.base}notices/${id}/`)
  }

  createNotice(payload: Partial<Notice>): Observable<Notice> {
    return this.http.post<Notice>(`${this.base}notices/`, payload)
  }

  getConsumeStatus(
    id: number
  ): Observable<{ status: string; document_id: number | null }> {
    return this.http.get<{ status: string; document_id: number | null }>(
      `${this.base}notices/${id}/consume-status/`
    )
  }

  notarize(
    id: number
  ): Observable<{ provider: string; status: string; signing_url: string | null }> {
    return this.http.post<{
      provider: string
      status: string
      signing_url: string | null
    }>(`${this.base}notices/${id}/notarize/`, {})
  }

  getNotarizeStatus(id: number): Observable<{
    provider: string
    status: string
    signed_document_url: string | null
  }> {
    return this.http.get<{
      provider: string
      status: string
      signed_document_url: string | null
    }>(`${this.base}notices/${id}/notarize-status/`)
  }

  listLegalSkills(): Observable<{ skills: LegalSkillSummary[] }> {
    return this.http.get<{ skills: LegalSkillSummary[] }>(
      `${this.base}legal-skills/`
    )
  }

  getLegalSkill(id: string): Observable<{ skill: LegalSkill }> {
    return this.http.get<{ skill: LegalSkill }>(`${this.base}legal-skills/${id}/`)
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
    }>(`${this.base}check-service-method/`, { method })
  }

  analyzeDocument(
    file: File,
    useDeepseekOcr = false
  ): Observable<DocumentAnalysisResult> {
    const formData = new FormData()
    formData.append('file', file)
    if (useDeepseekOcr) formData.append('use_deepseek_ocr', 'true')
    return this.http.post<DocumentAnalysisResult>(
      `${this.base}documents/analyze/`,
      formData
    )
  }
}
