import { defineStore } from 'pinia';
import { buildNotice, ALL_REASONS, isBreach, noticePeriodDays, BASE_PRICE_AED, ADD_ONS, calculateTotal } from '@rentshield/shared';

export const STEPS = [
  { title: 'Parties', icon: 'users' },
  { title: 'Property', icon: 'building-2' },
  { title: 'Notice & Reason', icon: 'calendar-clock' },
  { title: 'Review', icon: 'check-square' }
];

export const useNoticeStore = defineStore('notice', {
  state: () => ({
    step: 0,
    landlordName: '',
    tenantName: '',
    propertyType: 'Apartment',
    unitNo: '',
    buildingName: '',
    plotNumber: '',
    ejariNumber: '',
    noticeDate: new Date().toISOString().slice(0, 10),
    reason: '',
    addOns: { notarization: false, aiReview: false },
    paid: false,
    saving: false,
    saveError: null,
    savedId: null,
    savedNotices: [],

    // Paywall simulation modal
    showPaymentModal: false,
    paymentView: 'form' // 'form' | 'processing' | 'success'
  }),

  getters: {
    reasonData: (s) => ALL_REASONS[s.reason],
    isBreachReason: (s) => isBreach(s.reason),
    periodDays: (s) => noticePeriodDays(s.reason),
    document: (s) => buildNotice({
      landlordName: s.landlordName,
      tenantName: s.tenantName,
      propertyType: s.propertyType,
      unitNo: s.unitNo,
      buildingName: s.buildingName,
      plotNumber: s.plotNumber,
      ejariNumber: s.ejariNumber,
      noticeDate: s.noticeDate,
      reason: s.reason
    }),
    isReadyToSave: (s) => !!(s.landlordName && s.tenantName && s.noticeDate && s.reason),
    basePrice: () => BASE_PRICE_AED,
    addOnCatalog: () => ADD_ONS,
    totalPrice: (s) => calculateTotal(s.addOns)
  },

  actions: {
    goStep(delta) {
      const next = this.step + delta;
      if (next < 0 || next > STEPS.length - 1) return;
      this.step = next;
    },

    async saveNotice() {
      this.saving = true;
      this.saveError = null;
      try {
        const res = await fetch('/api/notices', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            landlordName: this.landlordName,
            tenantName: this.tenantName,
            propertyType: this.propertyType,
            unitNo: this.unitNo,
            buildingName: this.buildingName,
            plotNumber: this.plotNumber,
            ejariNumber: this.ejariNumber,
            noticeDate: this.noticeDate,
            reason: this.reason,
            addOns: this.addOns
          })
        });
        if (!res.ok) {
          const e = await res.json().catch(() => ({}));
          throw new Error(e.error || `Save failed (${res.status})`);
        }
        const data = await res.json();
        this.savedId = data.notice.id;
        await this.fetchSavedNotices();
        return data;
      } catch (err) {
        this.saveError = err.message;
        throw err;
      } finally {
        this.saving = false;
      }
    },

    async fetchSavedNotices() {
      try {
        const res = await fetch('/api/notices');
        if (!res.ok) return;
        const data = await res.json();
        this.savedNotices = data.notices;
      } catch {
        // Listing saved notices is a convenience, not load-bearing — fail quietly.
      }
    },

    openPaymentModal() {
      this.paymentView = 'form';
      this.showPaymentModal = true;
    },

    closePaymentModal() {
      this.showPaymentModal = false;
    },

    // Simulated Stripe-style checkout — no real payment rail, matches the
    // original prototype's paywall demo. Unblurs the document and prints.
    async completeFakePayment() {
      this.paymentView = 'processing';
      await new Promise((r) => setTimeout(r, 1800));
      this.paymentView = 'success';
      this.paid = true;
      await new Promise((r) => setTimeout(r, 1400));
      this.closePaymentModal();
      window.print();
    }
  }
});
