# CMS / Platform Comparison — Step N' Stones

Prepared to help decide how the site should be edited going forward. The goal is a setup
where **non-technical Japanese-speaking teachers** can update content (news, photos, page
text) easily, the **English-speaking owner** can also manage it, and editors can **log in
without needing a GitHub account**.

> **Note on pricing:** plan names and prices below are approximate and change often.
> Confirm current pricing on each vendor's site before deciding.

---

## The situation today

The site is a static **Jekyll** site (built from the old WordPress/SWELL export) with
**Decap CMS** for editing. Decap works, but it has hit structural limits for this project:

- It's **form-based**, not visual — no "click the photo and replace it" or drag-and-drop.
- Pages are raw exported HTML, so they aren't realistically editable by non-technical staff
  without first being rebuilt field-by-field.
- **Login requires a GitHub account** for each editor (its no-account option, "Git Gateway,"
  is deprecated by Netlify and would not enable on our site).

These three things are exactly what the teachers need, so it's worth comparing alternatives
rather than continuing to patch Decap.

## What stays the same regardless of choice

- **Hosting: Netlify** — all options below deploy to Netlify.
- **Recommended framework: Astro** — modern, Netlify-first, ingests the existing exported
  HTML far more easily than re-doing Jekyll, and integrates with every CMS below. The
  framework matters less than the CMS; Astro keeps all doors open.

---

## Comparison

| | **TinaCMS** | **Storyblok** | **Sanity** | **Builder.io** | *(Decap — today)* |
|---|---|---|---|---|---|
| **Editor experience** | Inline visual — click text on the live page; block sections | Polished visual editor, real-time preview, blocks | Structured editor + "Presentation" visual mode | True **drag-and-drop canvas** (most Elementor-like) | Forms only |
| **Ease for non-technical teachers** | Good | **Very good** | Good (more structured) | **Very good** (most freedom) | Limited |
| **Login (no GitHub needed)** | ✅ Email invite (TinaCloud) | ✅ Email invite + roles | ✅ Email invite + roles | ✅ Email invite | ❌ GitHub account each |
| **Japanese/English UI** | Content yes; admin UI mostly English | ✅ **Native JA/EN UI + multilingual content** | Content via plugins; UI mostly English | Supported | UI partial JA; no per-user toggle |
| **Where content lives** | **Your Git repo** (Markdown/JSON) | Storyblok cloud | Sanity cloud | Builder cloud | Your Git repo |
| **Lock-in / portability** | **Low** — content is in your repo | Medium — export via API | Medium — export via API | Medium–High | Low |
| **Cost** | Free self-host; TinaCloud free tier → paid seats | Free Community tier → paid plans | Generous free tier → per-seat | Free tier → paid (scales up) | Free |
| **Best fit when…** | You want to stay git-based & lean | You want the best teacher UX + bilingual | You want structured content + dev control | You want literal Elementor drag-drop | (current) |

---

## Short notes on each

**TinaCMS (+ Astro)** — Keeps content in your GitHub repo as Markdown/JSON, so **low
lock-in** and lowest cost. Gives inline visual editing and, via TinaCloud, **email invites**
so teachers don't need GitHub. Admin UI is mostly English. Best "keep it yours and lean" pick.

**Storyblok (+ Astro)** — A hosted (SaaS) headless CMS with a strong **visual editor**,
real-time preview, **built-in roles and email invites**, and **first-class Japanese/English**
support (both the editor UI and multilingual content). Best overall match for "English owner,
Japanese teachers, everyone edits." Content lives in Storyblok's cloud (export via API).

**Sanity (+ Astro)** — Very capable and developer-friendly, generous free tier, visual
"Presentation" mode. Slightly more structured/technical to set up than Storyblok; multilingual
needs plugins. Good if we want maximum control over content structure.

**Builder.io (+ Astro)** — The closest to **Elementor's drag-and-drop canvas**. Great freedom
for editors, but the most "page-builder" feel and the most potential for editors to alter
layout. SaaS with usage-based pricing that can grow.

**Decap (current)** — Free and git-based, but form-only, GitHub-login, and not suited to the
non-technical visual editing the customer wants.

---

## Migration effort (all options)

Any choice is a **one-time re-build**: rebuild the page templates in Astro and move content
into the new CMS. Two things make it manageable:

- The **265 news posts are already clean Markdown**, which ports easily (especially to Tina,
  which keeps Markdown in the repo).
- It's a **one-time investment** that finally matches what the customer wants, versus
  continually patching a setup that structurally can't get there.

Relative effort (lowest → highest content migration): **TinaCMS** (content stays as Markdown
in git) < **Sanity / Storyblok / Builder** (content imported into their hosted store).

---

## Recommendation

- **Best teacher experience + bilingual, small SaaS budget OK → Astro + Storyblok.**
- **Stay git-based and low-cost → Astro + TinaCMS.**
- **Must have literal drag-drop → Astro + Builder.io.**

**Suggested next step:** rather than commit blind, build a small **proof-of-concept** — Astro
+ the chosen CMS with the **home page, teacher page, and news** wired up, deployed to a
Netlify preview — so the owner and a teacher can actually *try editing* before approving the
full migration.
