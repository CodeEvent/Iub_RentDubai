import { CommonModule } from '@angular/common'
import { Component, inject, signal } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'
import { TourNgBootstrap } from 'ngx-ui-tour-ng-bootstrap'
import {
  LegalSkill,
  LegalSkillSummary,
  RentshieldApiService,
} from '../services/rentshield-api.service'

// Light Markdown -> HTML for skill bodies (headers, bold, lists only) —
// this is a reference panel, not a full renderer. Mirrors the same
// approach legacy-v1's ChatDrawer.vue used for the same content.
function renderSkillMarkdown(md: string): string {
  const esc = (s: string) =>
    s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')

  return md
    .split(/\n{2,}/)
    .map((block) => {
      const headerMatch = block.match(/^#{2,3}\s+(.+)$/m)
      if (headerMatch && block.trim().startsWith('#')) {
        return `<p class="fw-bold rs-navy mt-3">${esc(headerMatch[1])}</p>`
      }
      const lines = block.split('\n')
      if (lines.every((l) => /^(\d+\.|-)\s+/.test(l.trim()))) {
        const items = lines
          .map(
            (l) =>
              `<li>${esc(l.replace(/^(\d+\.|-)\s+/, '')).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</li>`
          )
          .join('')
        return `<ul>${items}</ul>`
      }
      return `<p>${esc(block).replace(/\n/g, ' ').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</p>`
    })
    .join('')
}

@Component({
  selector: 'app-legal-skills',
  standalone: true,
  imports: [CommonModule, NgxBootstrapIconsModule, TourNgBootstrap],
  templateUrl: './legal-skills.component.html',
  styleUrl: './legal-skills.component.scss',
})
export class LegalSkillsComponent {
  private api = inject(RentshieldApiService)

  skills = signal<LegalSkillSummary[]>([])
  selected = signal<LegalSkill | null>(null)
  selectedHtml = signal('')
  loadingSkill = signal(false)

  constructor() {
    this.api.listLegalSkills().subscribe((res) => {
      this.skills.set(res.skills)
      if (res.skills.length) this.select(res.skills[0].id)
    })
  }

  select(id: string): void {
    this.loadingSkill.set(true)
    this.api.getLegalSkill(id).subscribe({
      next: (res) => {
        this.selected.set(res.skill)
        this.selectedHtml.set(renderSkillMarkdown(res.skill.body))
        this.loadingSkill.set(false)
      },
      error: () => this.loadingSkill.set(false),
    })
  }
}
