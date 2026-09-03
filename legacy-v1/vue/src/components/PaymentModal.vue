<script setup>
import { ref, computed, watch } from 'vue';
import { ShieldCheck, X, CreditCard, Lock, Shield, Loader2, CheckCircle2 } from '@lucide/vue';
import { useNoticeStore } from '../stores/notice.js';

const store = useNoticeStore();

const cardholderName = ref('');
const cardNumber = ref('');
const expiry = ref('');
const cvc = ref('');

const selectedAddOns = computed(() =>
  Object.entries(store.addOnCatalog)
    .filter(([key]) => store.addOns[key])
    .map(([key, addOn]) => ({ key, ...addOn }))
);
const optionsTotal = computed(() => selectedAddOns.value.reduce((sum, a) => sum + a.priceAed, 0));
const amount = computed(() => store.totalPrice.toFixed(2));

function formatCardNumber(e) {
  const digits = e.target.value.replace(/\D/g, '').slice(0, 16);
  cardNumber.value = digits.replace(/(.{4})/g, '$1 ').trim();
}
function formatExpiry(e) {
  let v = e.target.value.replace(/\D/g, '').slice(0, 4);
  if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
  expiry.value = v;
}

function submitPayment() {
  store.completeFakePayment();
}

// Reset the form each time the modal opens fresh, so a previous card
// isn't left sitting in the fields when the tier or notice changes.
watch(
  () => store.showPaymentModal,
  (open) => {
    if (open) {
      store.paymentView = 'form';
      cardholderName.value = '';
      cardNumber.value = '';
      expiry.value = '';
      cvc.value = '';
    }
  }
);
</script>

<template>
  <div v-if="store.showPaymentModal" class="fixed inset-0 z-50">
    <div class="absolute inset-0 bg-slate950/60 backdrop-blur-sm" @click="store.closePaymentModal()"></div>

    <div class="relative min-h-full flex items-center justify-center p-4">
      <div class="relative w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div class="px-6 py-5 flex items-center justify-between" style="background: linear-gradient(120deg, #0f172a 0%, #1e293b 45%, #0f172a 100%);">
          <div class="flex items-center gap-2 text-white">
            <ShieldCheck class="w-5 h-5 text-emerald" />
            <span class="font-bold text-sm">Secure Checkout</span>
          </div>
          <button aria-label="Close checkout" class="text-slate-400 hover:text-white transition p-2 -m-2" @click="store.closePaymentModal()">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Form -->
        <div v-if="store.paymentView === 'form'" class="p-6">
          <div class="mb-5 rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden text-sm">
            <div class="flex items-center justify-between px-4 py-2.5">
              <span class="text-slate-500">Bilingual Notice Generator</span>
              <span class="font-semibold text-slate-800 tabular-nums">{{ store.basePrice.toFixed(2) }} AED</span>
            </div>
            <div v-for="a in selectedAddOns" :key="a.key" class="flex items-center justify-between px-4 py-2.5">
              <span class="text-slate-500">{{ a.label }}</span>
              <span class="font-semibold text-slate-800 tabular-nums">{{ a.priceAed.toFixed(2) }} AED</span>
            </div>
            <div class="flex items-center justify-between px-4 py-2.5 bg-slate-50">
              <span class="font-bold text-slate-900">Grand Total</span>
              <span class="text-xl font-extrabold text-slate950 tabular-nums">{{ amount }} <span class="text-sm font-semibold text-slate-400">AED</span></span>
            </div>
          </div>

          <form class="space-y-4" @submit.prevent="submitPayment">
            <div>
              <label class="text-xs font-semibold text-slate-600 mb-1 block">Cardholder Name</label>
              <input v-model="cardholderName" required type="text" placeholder="Ahmed Al Maktoum" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
            </div>
            <div>
              <label class="text-xs font-semibold text-slate-600 mb-1 block">Card Number</label>
              <div class="relative">
                <input :value="cardNumber" @input="formatCardNumber" required type="text" inputmode="numeric" maxlength="19" placeholder="4242 4242 4242 4242" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm pr-10">
                <CreditCard class="w-4 h-4 text-slate-400 absolute right-3.5 top-1/2 -translate-y-1/2" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs font-semibold text-slate-600 mb-1 block">Expiry</label>
                <input :value="expiry" @input="formatExpiry" required type="text" maxlength="5" placeholder="MM/YY" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
              </div>
              <div>
                <label class="text-xs font-semibold text-slate-600 mb-1 block">CVC</label>
                <input v-model="cvc" required type="text" inputmode="numeric" maxlength="4" placeholder="123" class="field-input w-full border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm">
              </div>
            </div>

            <button type="submit" class="w-full bg-slate950 hover:bg-slate-800 text-white font-bold text-sm py-3.5 rounded-xl transition flex items-center justify-center gap-2 mt-2">
              <Lock class="w-4 h-4" />
              <span>Pay {{ amount }} AED</span>
            </button>
            <p class="text-[10px] text-center text-slate-400 flex items-center justify-center gap-1">
              <Shield class="w-3 h-3" /> Simulated payment for prototype purposes only. No real charge occurs.
            </p>
          </form>
        </div>

        <!-- Processing -->
        <div v-else-if="store.paymentView === 'processing'" class="p-10 flex flex-col items-center justify-center gap-4 text-center">
          <div class="w-12 h-12 rounded-full bg-slate950 flex items-center justify-center">
            <Loader2 class="w-6 h-6 text-white animate-spin" />
          </div>
          <p class="font-semibold text-slate-700 text-sm">Processing your payment securely&hellip;</p>
          <p class="text-xs text-slate-400">Please do not close this window.</p>
        </div>

        <!-- Success -->
        <div v-else class="p-10 flex flex-col items-center justify-center gap-3 text-center">
          <div class="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center">
            <CheckCircle2 class="w-8 h-8 text-emerald-600" />
          </div>
          <p class="font-bold text-slate-900">Payment Successful</p>
          <p class="text-xs text-slate-400">Preparing your notarized document for print / download&hellip;</p>
        </div>
      </div>
    </div>
  </div>
</template>
