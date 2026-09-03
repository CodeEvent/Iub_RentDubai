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
    landlordEmail: '',
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

    // Real e-signature routing (DocuSeal primary, OpenSign fallback —
    // see api/src/services/esign/). Populated after saveNotice() when
    // the notarization add-on is selected.
    esignStatus: null,
    esignSigningUrl: null,
    esignError: null,
    requestingSignature: false,

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
    needsLandlordEmail: (s) => s.addOns.notarization && !s.landlordEmail,
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
            landlordEmail: this.landlordEmail,
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

    async requestNotarization() {
      if (!this.savedId) return;
      this.requestingSignature = true;
      this.esignError = null;
      try {
        const res = await fetch(`/api/notices/${this.savedId}/notarize`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `Notarization request failed (${res.status})`);
        this.esignStatus = data.status;
        this.esignSigningUrl = data.signingUrl;
      } catch (err) {
        this.esignError = err.message;
      } finally {
        this.requestingSignature = false;
      }
    },

    async refreshSigningStatus() {
      if (!this.savedId) return;
      try {
        const res = await fetch(`/api/notices/${this.savedId}/notarize/status`);
        if (!res.ok) return;
        const data = await res.json();
        this.esignStatus = data.status;
      } catch {
        // Status polling is a convenience — fail quietly, the user can retry.
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
      if (this.addOns.notarization) {
        if (!this.savedId) {
          try {
            await this.saveNotice();
          } catch {
            this.esignError = 'Could not save the notice, so notarization could not be requested.';
          }
        }
        if (this.savedId) await this.requestNotarization();
      }
      window.print();
    }
  }
});
