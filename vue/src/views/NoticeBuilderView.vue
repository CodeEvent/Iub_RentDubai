<script setup>
import WizardForm from '../components/WizardForm.vue';
import DocumentPreview from '../components/DocumentPreview.vue';
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
    <p class="text-sm text-slate-500 mb-6 max-w-2xl">Generate a bilingual (English &amp; Arabic) notice compliant with Dubai Law No. (33) of 2008, ready for Notary Public service.</p>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <section>
        <WizardForm />
        <div class="mt-5 flex gap-3 items-start bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3.5">
          <p class="text-xs text-emerald-800 leading-relaxed">This tool auto-calculates the mandatory <strong>365-day</strong> (or <strong>30-day</strong> breach) notice period per Article 25 and enforces the statutory eviction and breach grounds recognized by RERA / the Rental Dispute Settlement Centre (RDSC).</p>
        </div>
      </section>
      <section>
        <DocumentPreview />
      </section>
    </div>
  </div>
</template>
