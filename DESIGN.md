# RentShield onboarding & passkey design system

Scope: the passwordless sign-in/sign-up wizard (`documents/templates/rentshield/signup_*.html`)
and the passkey registration bridge (`authelia/nginx/rentshield-bridge/index.html`). Not the
paperless-ngx document/admin UI, which keeps its own existing look.

This replaces the previous GOV.UK-influenced skin on these same pages. The interaction pattern
(one question per screen, linear back/continue, no competing calls to action) is kept — only
the visual language changes.

## Why this look

The subject here is custody of legal documents (tenancy contracts, notarizations) gated by a
hardware-bound biometric credential, not a general-purpose SaaS trial signup. The one moment
worth spending visual weight on is the passkey ceremony itself — the instant a fingerprint or
Face ID scan hands back a cryptographic credential. Everything else stays quiet so that moment
reads as deliberate, not decorated.

## Color

| Token | Hex | Use |
|---|---|---|
| `--rs-bg` | `#09090b` | Page background (void-black) |
| `--rs-surface` | `#18181b` | Card surface |
| `--rs-border` | `#27272a` | 1px hairline borders |
| `--rs-text` | `#e8eaed` | Primary text |
| `--rs-text-muted` | `#8b93a1` | Secondary text, hints |
| `--rs-accent` | `#7c6cf6` | Primary actions, focus rings, links |
| `--rs-accent-strong` | `#9b8cff` | Hover state of the above |
| `--rs-verified` | `#10b981` | Success / verified state only -- never a button/link/focus color |
| `--rs-danger` | `#fb7185` | Errors |
| `--rs-danger-bg` | `#2a1215` | Error banner background |

No gradients, no drop shadows except the deliberate glow described below. Borders are exactly
1px and always `--rs-border` at rest.

## Type

One family for everything: the system UI sans stack (`-apple-system, "Segoe UI", Inter,
sans-serif` as fallback chain) — no webfont fetch on a login screen, which would add an
external network dependency to the one page that most needs to work offline/on a flaky
connection.

Monospace (`ui-monospace, "SF Mono", "Cascadia Code", monospace`) is reserved for exactly two
things: the 6-digit verification code input, and any future rendering of security metadata
(credential IDs, tag names like "Awaiting Notary Public"). Not used for labels or body copy.

Scale: 26px/1.25 for the single `h1` per screen, 15px/1.5 body, 13px hints/labels. No tracked-out
uppercase eyebrows.

## Layout

Single centered card, `max-width: 26rem`, left-aligned text throughout (this is a form, not a
poster). One screen, one question, one primary action — kept from the prior design. The card
itself (`.rs-card`) is a real bordered panel now on every page, not just the bridge page — same
treatment, same tokens, so the wizard and the ceremony page read as one system.

```
┌──────────────────────────────┐
│ ← Back                        │
│                                │
│ Step 1 of 4                    │
│ Enter your email address        │
│ We'll send a 6-digit code…       │
│                                │
│ Email address                   │
│ ┌──────────────────────────┐    │
│ └──────────────────────────┘    │
│ ☐ I agree to terms                │
│                                │
│ ┌───────────┐                   │
│ │ Continue  │                   │
│ └───────────┘                   │
└──────────────────────────────┘
```

The step count (`Step 1 of 4`) is real — the flow is a genuine fixed sequence — so it stays,
in sentence case, not as a decorative numbered-circle stepper.

## Components & states

**Text input**
- Rest: `1px solid var(--rs-border)`, `background: var(--rs-surface)`.
- Focus: border becomes `var(--rs-accent)` + a tight glow (`box-shadow: 0 0 0 3px rgba(124,108,246,.25)`), no color change on the whole field.
- Error: border `var(--rs-danger)`, no glow.
- The OTP code field additionally gets `font-family: var(--rs-font-mono)`, letter-spacing `.3em`, centered digits.

**Button (primary)**
- Rest: solid `var(--rs-accent)` fill, `var(--rs-bg)` text (dark text on light-purple reads as more deliberate than white-on-purple here).
- Hover: `var(--rs-accent-strong)`.
- Disabled/loading: fill drops to 55% opacity, cursor `not-allowed`, label replaced by a spinner glyph — button never disappears or resizes.
- Focus-visible: same glow treatment as inputs, for keyboard users.

**Button (secondary / link-style)**
- No fill, `var(--rs-text-muted)`, underline on hover only.

**Error banner**
- `background: var(--rs-danger-bg)`, `border-left: 3px solid var(--rs-danger)`, text `var(--rs-danger)`. Written in plain language stating what happened and what to do next — never "an error occurred."

**Card (any page)**
- Rest: `var(--rs-surface)` fill, `var(--rs-border)` hairline.
- `:focus-within`: border becomes `var(--rs-accent)` with a very subtle glow (`box-shadow: 0 0 0 3px rgba(124,108,246,.12)`, a quarter the opacity of the input/button focus glow) — enough to read as "you're inside this panel," not enough to compete with the field's own focus ring.

**Passkey ceremony card (bridge page only)**
- Idle: shows the action explained in one sentence + the primary button.
- In-flight: button shows the spinner state above; a short status line beneath swaps to "Waiting for your device…".
- Success: border transitions to `var(--rs-verified)` (emerald, `#10b981`) with the glow treatment in emerald instead of violet — this is the one moment in the whole flow that gets a color outside the violet/red pair, because it is the payoff. Emerald never appears anywhere else — not as a hover tint, not as a focus ring — so this moment stays legible as "the ceremony actually succeeded," not just "you're hovering something."
- Failure (including the user cancelling the OS biometric prompt, or the client-side `AbortSignal` timeout firing because the browser never got a device to ask): the error banner above, plus the button resets to idle so they can retry without reloading.

## Motion

One transition, used twice: a 150ms ease-out on border-color/box-shadow for focus and for the
success-state color swap on the bridge page. No entrance animations, no hover transforms on
static content — nothing here should move unless it's answering something the person just did.

## Accessibility floor

Visible focus ring on every interactive element (the glow treatment doubles as this). Error
text is never color-only — it's also a written sentence. Contrast: `--rs-text` on `--rs-bg` is
14.1:1; `--rs-accent` on `--rs-bg` is 5.2:1, sufficient for large text/icons but body copy stays
on `--rs-text`/`--rs-text-muted`, not accent color. Respects `prefers-reduced-motion` (the one
transition above is disabled, not accelerated).
