#!/usr/bin/env node
// Real MCP server — this is the actual integration point the prototype's
// "RentShield AI" chat panel only simulated locally. Any MCP-aware client
// (Claude Desktop, Claude Code, etc.) can attach to this over stdio and
// call these tools directly against the same shared/ legal logic the API
// and Vue app use, so answers are never hallucinated math or wording.
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { ALL_REASONS, isBreach, noticePeriodDays, buildNotice } from '@rentshield/shared';
import { loadSkills } from './loadSkills.js';

const server = new McpServer({ name: 'rentshield', version: '1.0.0' });

const REASON_KEYS = Object.keys(ALL_REASONS);
const SKILLS = loadSkills();
const SKILL_IDS = SKILLS.map((s) => s.id);

server.registerTool(
  'list_statutory_reasons',
  {
    title: 'List Dubai eviction/breach statutory reasons',
    description: 'Lists the recognized grounds for a Dubai tenancy notice under Law No. (33) of 2008 — the four 12-month statutory eviction grounds (sale, personal use, demolition, renovation) and the two 30-day Article 25(1) breach grounds (non-payment, unauthorized subleasing) — with their labels and compliance warnings.',
    inputSchema: {}
  },
  async () => ({
    content: [{ type: 'text', text: JSON.stringify(ALL_REASONS, null, 2) }]
  })
);

server.registerTool(
  'calculate_notice_expiry',
  {
    title: 'Calculate a notice\'s legal expiry/compliance date',
    description: 'Given a notice-served date and a statutory reason key, returns the mandatory notice period (365 days for the four eviction grounds, 30 days for the two Article 25(1) breach grounds) and the resulting expiry/compliance date.',
    inputSchema: {
      noticeDate: z.string().describe('ISO date (YYYY-MM-DD) the notice was served'),
      reason: z.enum(REASON_KEYS).describe('One of: ' + REASON_KEYS.join(', '))
    }
  },
  async ({ noticeDate, reason }) => {
    const days = noticePeriodDays(reason);
    const expiry = new Date(noticeDate + 'T00:00:00');
    expiry.setDate(expiry.getDate() + days);
    const result = {
      noticeDate,
      reason,
      reasonLabel: ALL_REASONS[reason]?.label,
      noticeType: isBreach(reason) ? '30-day breach notice (Article 25(1))' : '12-month statutory notice (Article 25(2))',
      noticePeriodDays: days,
      expiryDate: expiry.toISOString().slice(0, 10)
    };
    return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
  }
);

server.registerTool(
  'draft_eviction_notice',
  {
    title: 'Draft a bilingual Dubai eviction or breach notice',
    description: 'Drafts the full bilingual (English + Legal Arabic) statutory notice text for a given landlord/tenant/property/reason, choosing the correct 12-month or 30-day template automatically based on the reason.',
    inputSchema: {
      landlordName: z.string(),
      tenantName: z.string(),
      propertyType: z.string().optional().default('Apartment'),
      unitNo: z.string().optional(),
      buildingName: z.string().optional(),
      plotNumber: z.string().optional(),
      ejariNumber: z.string().optional(),
      noticeDate: z.string().describe('ISO date (YYYY-MM-DD)'),
      reason: z.enum(REASON_KEYS)
    }
  },
  async (input) => {
    const document = buildNotice(input);
    return { content: [{ type: 'text', text: JSON.stringify(document, null, 2) }] };
  }
);

// --- Legal skills library (mcp/skills/) — see loadSkills.js for the
// convention this borrows from legal-skills-open / agentcounsel. This
// widens RentShield AI beyond notice drafting into adjacent UAE tenancy
// questions (RDSC filing, deposit disputes, valid service methods)
// without inventing legal content on the fly — every answer traces back
// to a reviewable file in the repo.
server.registerTool(
  'list_legal_skills',
  {
    title: 'List available UAE tenancy legal-guidance skills',
    description: 'Lists the reference guidance skills available beyond notice drafting — e.g. RDSC filing, security deposit disputes, valid notice service methods — each with a short summary and its practice area.',
    inputSchema: {}
  },
  async () => ({
    content: [{
      type: 'text',
      text: JSON.stringify(SKILLS.map(({ id, title, jurisdiction, practice_area }) => ({ id, title, jurisdiction, practice_area })), null, 2)
    }]
  })
);

server.registerTool(
  'get_legal_skill',
  {
    title: 'Get the full text of a UAE tenancy legal-guidance skill',
    description: 'Returns the full reference guidance for one skill from list_legal_skills, including its disclaimer.',
    inputSchema: { id: z.enum(SKILL_IDS) }
  },
  async ({ id }) => {
    const skill = SKILLS.find((s) => s.id === id);
    return { content: [{ type: 'text', text: JSON.stringify(skill, null, 2) }] };
  }
);

const SERVICE_METHODS = {
  notary_public: { valid: true, label: 'Notary Public' },
  registered_mail: { valid: true, label: 'Registered mail with acknowledgment of receipt' },
  court_bailiff: { valid: true, label: 'Court bailiff (محضر)' },
  whatsapp: { valid: false, label: 'WhatsApp / SMS' },
  email: { valid: false, label: 'Plain (non-registered) email' },
  verbal: { valid: false, label: 'Verbal notice' },
  hand_delivery_unwitnessed: { valid: false, label: 'Hand delivery without notarization or a witnessed receipt' }
};

server.registerTool(
  'check_notice_service_method_validity',
  {
    title: 'Check whether a notice service method satisfies Article 25(3)',
    description: 'Given how a landlord served (or intends to serve) a tenancy notice, reports whether that method is one of the three recognized under Article 25(3) of Law No. (33) of 2008 (Notary Public, registered mail, or court bailiff) and briefly why, drawing on the notice-service-method-uae skill.',
    inputSchema: { method: z.enum(Object.keys(SERVICE_METHODS)).describe('How the notice was/will be served') }
  },
  async ({ method }) => {
    const m = SERVICE_METHODS[method];
    const result = {
      method: m.label,
      isValidUnderArticle25_3: m.valid,
      note: m.valid
        ? 'Recognized under Article 25(3) — keep the notarized certificate / registered-mail receipt / bailiff report as proof of service for any later RDSC filing.'
        : 'Not one of the three methods Article 25(3) recognizes. A notice served this way is likely to be challenged as invalid — re-serve using a Notary Public, registered mail, or a court bailiff.'
    };
    return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
