<script setup>
import AppHeader from './components/AppHeader.vue';
import WizardForm from './components/WizardForm.vue';
import DocumentPreview from './components/DocumentPreview.vue';
import SavedNotices from './components/SavedNotices.vue';
import ChatDrawer from './components/ChatDrawer.vue';
import PaymentModal from './components/PaymentModal.vue';
</script>

<template>
  <AppHeader />

  <div class="bg-white border-b border-slate-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
      <h1 class="text-xl sm:text-2xl font-extrabold text-slate950 tracking-tight">12-Month Statutory Eviction Notice Generator</h1>
      <p class="text-sm text-slate-500 mt-1">Generate a bilingual (English &amp; Arabic) notice compliant with Dubai Law No. (33) of 2008, ready for Notary Public service.</p>
    </div>
  </div>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
    <section>
      <WizardForm />
      <div class="mt-5 flex gap-3 items-start bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3.5">
        <p class="text-xs text-emerald-800 leading-relaxed">This tool auto-calculates the mandatory <strong>365-day</strong> (or <strong>30-day</strong> breach) notice period per Article 25 and enforces the statutory eviction and breach grounds recognized by RERA / the Rental Dispute Settlement Centre (RDSC).</p>
      </div>
    </section>
    <section>
      <DocumentPreview />
    </section>
  </main>

  <SavedNotices />

  <footer class="border-t border-slate-200 bg-white">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-xs text-slate-400">
      Dubai Rent Shield is a document drafting aid and does not constitute legal advice. Always verify service requirements with a licensed UAE legal counsel or Notary Public.
    </div>
  </footer>

  <ChatDrawer />
  <PaymentModal />
</template>
