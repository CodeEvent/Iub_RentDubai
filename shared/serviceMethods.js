/* Recognized methods of serving a Dubai tenancy notice under Article
   25(3) of Law No. (33) of 2008 — the single source of truth shared by
   the MCP check_notice_service_method_validity tool
   (mcp/src/server.js), the notice-service-method-uae skill
   (mcp/skills/), and the citation-graph document analysis
   (shared/citationGraph.js), so all three agree on the same list
   instead of drifting. */
export const SERVICE_METHODS = {
  notary_public: { valid: true, label: 'Notary Public', pattern: /notary\s+public|k[aā]tib\s+al-?adl|كاتب\s+العدل/i },
  registered_mail: { valid: true, label: 'Registered mail with acknowledgment of receipt', pattern: /registered\s+mail|recorded\s+delivery/i },
  court_bailiff: { valid: true, label: 'Court bailiff (محضر)', pattern: /court\s+bailiff|محضر/i },
  whatsapp: { valid: false, label: 'WhatsApp / SMS', pattern: /whatsapp|\bsms\b|text\s+message/i },
  email: { valid: false, label: 'Plain (non-registered) email', pattern: /\be-?mail\b/i },
  verbal: { valid: false, label: 'Verbal notice', pattern: /verbal(ly)?\s+notic|orally\s+inform/i },
  hand_delivery_unwitnessed: { valid: false, label: 'Hand delivery without notarization or a witnessed receipt', pattern: /hand[\s-]?deliver(ed|y)/i }
};
