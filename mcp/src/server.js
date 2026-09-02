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

const server = new McpServer({ name: 'rentshield', version: '1.0.0' });

const REASON_KEYS = Object.keys(ALL_REASONS);

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

const transport = new StdioServerTransport();
await server.connect(transport);
