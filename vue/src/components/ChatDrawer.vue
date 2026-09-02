<script setup>
import { ref, nextTick } from 'vue';
import { MessageCircle, X, Bot, Sparkles, Paperclip, Send, UploadCloud, Lock } from '@lucide/vue';
import { ALL_REASONS, isBreach } from '@rentshield/shared';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();

/* ---------------------------------------------------------
   This is a locally-simulated agent (no network calls, no API
   key in the browser) — see mcp/src/server.js for the real MCP
   tools a hosted LLM would actually call. The behavioral rules
   below (Dubai-only focus, hedged legal language, the 12-month
   vs 30-day distinction) mirror that server's tool descriptions
   so the simulated and real integration paths agree.
   --------------------------------------------------------- */

const open = ref(false);
const messages = ref([]);
const quickReplies = ref([]);
const stage = ref('idle'); // idle -> landlord -> tenant -> ejari -> reason -> done
const tierBannerVisible = ref(false);
const inputText = ref('');
const chatInput = ref(null);
const messagesEl = ref(null);
const dragActive = ref(false);
const fileInputEl = ref(null);
let dragCounter = 0;
let idCounter = 0;

const REASON_LABELS = Object.values(ALL_REASONS).map((r) => r.label);
const OFF_TOPIC_RE = /\b(weather|joke|football|cricket score|recipe|stock market|share price|movie|song lyrics|write (a |me )?(poem|code|program)|python tutorial|javascript tutorial|crypto|bitcoin|capital of|who won)\b/i;

const toastMsg = ref('');
const toastVisible = ref(false);
let toastTimer;
function showToast(msg) {
  toastMsg.value = msg;
  toastVisible.value = true;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastVisible.value = false), 2200);
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}

function pushUserMessage(text) {
  messages.value.push({ id: idCounter++, sender: 'user', text });
  scrollToBottom();
}
function pushAiMessage(html) {
  const msg = { id: idCounter++, sender: 'ai', html };
  messages.value.push(msg);
  scrollToBottom();
  return msg;
}
function pushUpsell(pkgLabel) {
  messages.value.push({ id: idCounter++, sender: 'ai', upsell: true, pkgLabel });
  scrollToBottom();
}
function pushTyping() {
  const msg = { id: idCounter++, sender: 'ai', typing: true };
  messages.value.push(msg);
  scrollToBottom();
  return msg.id;
}
function removeMessage(id) {
  messages.value = messages.value.filter((m) => m.id !== id);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function stagePrompt(s) {
  return {
    landlord: "Could you tell me the Landlord's full name?",
    tenant: "Could you tell me the Tenant's full name?",
    ejari: 'Could you share the Ejari Certificate Number?',
    reason: 'What is the core reason for the eviction?'
  }[s] || '';
}

function extractName(text) {
  let t = text.replace(/^(the\s+)?(landlord|tenant)('s)?\s+(is|name is|full name is)\s*[:\-]?\s*/i, '').trim();
  t = t.replace(/^(it'?s|it is|my name is|i am|i'?m)\s+/i, '').trim();
  if (!t) t = text.trim();
  return t.replace(/[.!]+$/, '');
}
function extractEjari(text) {
  const m = text.match(/[a-zA-Z0-9-]{6,}/);
  return m ? m[0] : text.trim();
}

function showReasonQuickReplies() {
  quickReplies.value = REASON_LABELS;
}

function handleSend(raw) {
  const text = (raw || '').trim();
  if (!text) return;
  pushUserMessage(text);
  quickReplies.value = [];

  const typingId = pushTyping();
  setTimeout(() => {
    removeMessage(typingId);
    routeIntake(text);
  }, 650 + Math.random() * 500);
}

function routeIntake(text) {
  if (OFF_TOPIC_RE.test(text)) {
    pushAiMessage(`I am programmed exclusively to assist with Dubai real estate rental compliance. ${stagePrompt(stage.value === 'idle' ? 'landlord' : stage.value)}`);
    if (stage.value === 'reason') showReasonQuickReplies();
    return;
  }

  switch (stage.value) {
    case 'idle':
    case 'landlord': {
      store.landlordName = extractName(text);
      showToast('✅ Form updated from AI chat');
      pushAiMessage(`Got it — <strong>${escapeHtml(store.landlordName)}</strong> noted as the Landlord. And what's the <strong>Tenant's full name</strong>?`);
      stage.value = 'tenant';
      break;
    }
    case 'tenant': {
      store.tenantName = extractName(text);
      showToast('✅ Form updated from AI chat');
      pushAiMessage(`Thank you. Could you share the <strong>Ejari Certificate Number</strong> for this tenancy?`);
      stage.value = 'ejari';
      break;
    }
    case 'ejari': {
      store.ejariNumber = extractEjari(text);
      showToast('✅ Form updated from AI chat');
      pushAiMessage(`Perfect. Now, what is the <strong>core reason for eviction</strong>? Choose one below, or describe it in your own words.`);
      showReasonQuickReplies();
      stage.value = 'reason';
      break;
    }
    case 'reason': {
      handleReasonAnswer(text);
      break;
    }
    default: {
      pushAiMessage(`Your data is already compiled. This appears consistent with a complete RERA-ready package — click "Generate Package" above, or upload a tenancy contract addendum if you'd like me to cross-check custom clauses.`);
    }
  }
}

function handleReasonAnswer(text) {
  const lower = text.toLowerCase();
  let matched = null;
  if (/sale|sell/.test(lower)) matched = 'sale';
  else if (/personal|recover|own use|move in/.test(lower)) matched = 'personal';
  else if (/demoli/.test(lower)) matched = 'demolition';
  else if (/renovat|refurbish/.test(lower)) matched = 'renovation';
  else if (/non-?payment|unpaid rent|didn'?t pay|rent arrears|arrears/.test(lower)) matched = 'nonpayment';
  else if (/sublet|subleas|unauthoriz(ed)? occup|airbnb/.test(lower)) matched = 'sublease';

  if (!matched) {
    pushAiMessage(`I couldn't confidently match that to a recognized statutory ground. Please choose one of the options below.`);
    showReasonQuickReplies();
    return;
  }

  store.reason = matched;
  showToast('✅ Form updated from AI chat');
  const r = ALL_REASONS[matched];

  if (isBreach(matched)) {
    pushAiMessage(`This appears to fall under Article 25(1) of Law No. (33) of 2008 — <strong>${r.label}</strong> is a lease-breach ground that only requires a <strong>30-day notice</strong>, not the 12-month statutory notice. I've switched your document to a 30-Day Breach Notice and kept the Landlord/Tenant/Ejari details you already gave me.`);
  } else {
    let extra = '';
    if (matched === 'personal') {
      extra = ' <strong>⚠️ Important:</strong> you will not be permitted to re-lease this property to a new tenant for 2 consecutive years from the eviction date.';
    } else if (matched === 'sale') {
      extra = ' Note that you should be able to demonstrate genuine intent to sell if this is challenged.';
    } else {
      extra = ' A technical report or government approval will likely be needed to support this ground at the RDSC.';
    }
    pushAiMessage(`This appears consistent with a valid statutory ground under Article 25 — <strong>${r.label}</strong>.${extra}`);
  }
  stage.value = 'done';
  setTimeout(triggerUpsell, 900);
}

function triggerUpsell() {
  const pkgLabel = isBreach(store.reason) ? '30-day breach notice' : '12-month eviction notice';
  const typingId = pushTyping();
  setTimeout(() => {
    removeMessage(typingId);
    pushUpsell(pkgLabel);
  }, 900);
}

function handleGeneratePackage() {
  closeDrawer();
  store.step = 3;
  store.openPaymentModal();
}

/* ---------- Document upload (OCR simulation) — click OR drag-and-drop ---------- */
function processUploadedFile(file) {
  if (!file) return;
  pushUserMessage(`📎 Uploaded: ${file.name}`);
  const typingId = pushAiMessage(`<span class="inline-flex items-center gap-2"><span class="spinner-sm"></span> AI reading tenancy contract addendum&hellip;</span>`).id;

  setTimeout(() => {
    removeMessage(typingId);
    renderDocAnalysisCard();
  }, 2000);
}

function renderDocAnalysisCard() {
  pushAiMessage(`
    <div class="space-y-2">
      <p class="font-bold text-slate-900">📁 Document Detected: Ejari Tenancy Addendum</p>
      <p class="text-slate-700">🔍 <strong>Key Findings:</strong> Found a clause stating <em>"60 days notice for vacation."</em></p>
      <div class="bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-red-800 text-[12px] leading-relaxed">
        ⚠️ <strong>RERA Compliance Alert:</strong> This clause violates Dubai Law No. (33) of 2008. Your notice will be legally invalid at the RDSC unless you serve a full statutory 12-month notice.
      </div>
    </div>`);

  store.tier = 'premium';
  tierBannerVisible.value = true;

  let autoFilledNote = '';
  if (!store.ejariNumber) {
    store.ejariNumber = 'EJR-2024-778193';
    showToast('✅ Form updated from AI chat');
    autoFilledNote = ` I've also auto-filled the Ejari Certificate Number I found in the document (<strong>EJR-2024-778193</strong>) into your notice form.`;
  }

  setTimeout(() => {
    const typingId = pushTyping();
    setTimeout(() => {
      removeMessage(typingId);
      pushAiMessage(`This appears to void the 60-day clause in favor of the mandatory 12-month statutory notice — this is consistent with RERA guidelines on public policy overriding private contract terms.${autoFilledNote} Your <strong>Premium AI Tier</strong> is now active, including this custom clause review in your downloadable package.`);
      showToast('✨ Premium AI Tier unlocked');
    }, 900);
  }, 400);
}

function onFileInputChange(e) {
  const file = e.target.files[0];
  e.target.value = '';
  processUploadedFile(file);
}
function onDragEnter(e) {
  e.preventDefault();
  dragCounter++;
  dragActive.value = true;
}
function onDragOver(e) {
  e.preventDefault();
}
function onDragLeave() {
  dragCounter = Math.max(0, dragCounter - 1);
  if (dragCounter === 0) dragActive.value = false;
}
function onDrop(e) {
  e.preventDefault();
  dragCounter = 0;
  dragActive.value = false;
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  processUploadedFile(file);
}

/* ---------- Drawer open/close + intake kickoff ---------- */
function openDrawer() {
  open.value = true;
  if (stage.value === 'idle') {
    setTimeout(() => {
      const typingId = pushTyping();
      setTimeout(() => {
        removeMessage(typingId);
        pushAiMessage(`👋 Hi, I'm <strong>RentShield AI</strong> — I specialize exclusively in Dubai rental law compliance. I can gather your notice details here, or you can upload a tenancy document for me to review.<br><br>Let's start: what is the <strong>Landlord's full name</strong>?`);
        stage.value = 'landlord';
      }, 800);
    }, 300);
  }
  nextTick(() => chatInput.value?.focus());
}
function closeDrawer() {
  open.value = false;
}
function toggleDrawer() {
  open.value ? closeDrawer() : openDrawer();
}

function submitInput() {
  handleSend(inputText.value);
  inputText.value = '';
}

defineExpose({ openDrawer, closeDrawer });
</script>

<template>
  <button
    aria-label="Open RentShield AI chat"
    class="fixed z-40 w-14 h-14 rounded-full bg-slate950 hover:bg-slate-800 text-white shadow-2xl flex items-center justify-center transition"
    style="bottom: calc(1.25rem + env(safe-area-inset-bottom)); right: calc(1.25rem + env(safe-area-inset-right)); box-shadow: 0 20px 40px -15px rgba(15,23,42,0.4);"
    @click="toggleDrawer"
  >
    <MessageCircle class="w-6 h-6" />
  </button>

  <div v-if="open" class="fixed inset-0 bg-slate950/30 z-30" @click="closeDrawer"></div>

  <div
    id="chatDrawer"
    class="fixed inset-y-0 right-0 z-40 w-full sm:w-[400px] bg-white shadow-2xl border-l border-slate-200 flex flex-col transition-transform duration-300"
    :class="[open ? 'translate-x-0' : 'translate-x-full', { 'drag-active': dragActive }]"
    style="padding-right: env(safe-area-inset-right);"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="px-5 py-4 flex items-center justify-between shrink-0" style="background: linear-gradient(120deg, #0f172a 0%, #1e293b 45%, #0f172a 100%);">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-full bg-emerald/20 flex items-center justify-center relative shrink-0">
          <Bot class="w-5 h-5 text-emerald" />
          <span class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald rounded-full ring-2 ring-slate950"></span>
        </div>
        <div>
          <p class="text-white font-bold text-sm leading-tight">RentShield AI</p>
          <p class="text-[10px] text-slate-400">Dubai RERA Compliance Agent</p>
        </div>
      </div>
      <button aria-label="Close chat" class="text-slate-400 hover:text-white transition p-2 -m-2" @click="closeDrawer">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div v-if="tierBannerVisible" class="px-4 py-2 bg-amber-50 border-b border-amber-100 text-[11px] text-amber-800 font-semibold flex items-center gap-1.5 shrink-0">
      <Sparkles class="w-3.5 h-3.5" /> Premium AI Tier unlocked &mdash; document analyzed
    </div>

    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-slate-50">
      <template v-for="m in messages" :key="m.id">
        <div v-if="m.typing" class="flex justify-start">
          <div class="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3.5 flex gap-1.5 shadow-sm">
            <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
          </div>
        </div>
        <div v-else-if="m.sender === 'user'" class="flex justify-end">
          <div class="max-w-[85%] bg-slate950 text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm">{{ m.text }}</div>
        </div>
        <div v-else-if="m.upsell" class="flex justify-start">
          <div class="max-w-[85%] bg-white text-slate-800 border border-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm">
            I have verified your data against RERA compliance. I'm ready to compile your official bilingual (English &amp; Legal Arabic) {{ m.pkgLabel }} package.
            <div class="mt-2.5 space-y-1.5">
              <div class="text-[11px] bg-slate-50 border border-slate-200 rounded-lg p-2.5"><strong>Standard &mdash; 99 AED:</strong> Instant bilingual notice.</div>
              <div class="text-[11px] bg-emerald-50 border border-emerald-200 rounded-lg p-2.5"><strong>Premium AI &mdash; 249 AED:</strong> + Ejari contract analysis &amp; custom clause review.</div>
            </div>
            <button class="mt-3 w-full bg-emerald hover:bg-emerald-600 text-white text-xs font-bold py-2.5 rounded-xl transition" @click="handleGeneratePackage">Generate Package &rarr;</button>
          </div>
        </div>
        <div v-else class="flex justify-start">
          <div class="max-w-[85%] bg-white text-slate-800 border border-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm" v-html="m.html"></div>
        </div>
      </template>
    </div>

    <div v-if="quickReplies.length" class="px-4 pb-3 flex flex-wrap gap-2 bg-slate-50">
      <button
        v-for="label in quickReplies"
        :key="label"
        class="chat-chip text-[11px] font-semibold bg-white border border-slate-300 text-slate-600 rounded-full px-3 py-1.5"
        @click="handleSend(label)"
      >{{ label }}</button>
    </div>

    <div class="chat-input-bar border-t border-slate-200 bg-white p-3 shrink-0" style="padding-bottom: calc(0.75rem + env(safe-area-inset-bottom));">
      <div class="flex items-end gap-2">
        <input ref="fileInputEl" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" class="hidden" @change="onFileInputChange">
        <button title="Upload Document (PDF/Image)" type="button" class="shrink-0 w-10 h-10 rounded-xl border border-slate-200 hover:bg-slate-100 flex items-center justify-center transition text-slate-500" @click="fileInputEl.click()">
          <Paperclip class="w-4 h-4" />
        </button>
        <input
          ref="chatInput"
          v-model="inputText"
          type="text"
          placeholder="Type your message..."
          class="field-input flex-1 border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm"
          @keydown.enter.prevent="submitInput"
        >
        <button type="button" class="shrink-0 w-10 h-10 rounded-xl bg-slate950 hover:bg-slate-800 text-white flex items-center justify-center transition" @click="submitInput">
          <Send class="w-4 h-4" />
        </button>
      </div>
      <p class="text-[10px] text-slate-400 mt-1.5 text-center">Simulated locally for this prototype &middot; Not legal advice</p>
    </div>

    <div v-if="dragActive" class="absolute inset-0 z-10 bg-emerald-600/90 flex flex-col items-center justify-center gap-2 text-white pointer-events-none">
      <UploadCloud class="w-9 h-9" />
      <p class="font-bold text-sm">Drop tenancy document to analyze</p>
      <p class="text-[11px] text-emerald-50">PDF, image, or WhatsApp export</p>
    </div>
  </div>

  <div
    class="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 bg-slate950 text-white text-xs font-semibold px-4 py-2.5 rounded-full shadow-xl transition-opacity duration-300"
    :class="toastVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'"
  >{{ toastMsg }}</div>
</template>
