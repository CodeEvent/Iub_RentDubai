/* Service pricing — a base self-serve generator fee plus optional add-on
   services, modeled after how Dubai legal-document services (e.g.
   jurist.ae's Tenant Eviction Notice product: a base price plus checkbox
   add-ons like Apostille, Attestation, and Express Service) structure
   their checkout, but priced for what this actually is: an instant
   self-serve document generator, not a law firm. We're not competing on
   being cheaper lawyers — the AED thousands those services charge cover
   real human legal drafting, physical notarization, and process-serving
   labor that this platform doesn't perform itself. */

export const BASE_PRICE_AED = 95;

export const ADD_ONS = {
  notarization: {
    label: 'Notarization Service',
    description: 'Route your notice through a licensed UAE notary for physical notarization before service.',
    priceAed: 249
  },
  aiReview: {
    label: 'AI Compliance Review',
    description: 'Upload your tenancy contract addendum for automated clause analysis against Dubai Law No. (33) of 2008.',
    priceAed: 99
  }
};

export function calculateTotal(selectedAddOns = {}) {
  let total = BASE_PRICE_AED;
  for (const key of Object.keys(ADD_ONS)) {
    if (selectedAddOns[key]) total += ADD_ONS[key].priceAed;
  }
  return total;
}
