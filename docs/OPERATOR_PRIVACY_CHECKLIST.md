# Campus — Operator Privacy Checklist

For the school / daycare running Campus. Campus provides the technical
controls; this checklist is the operational and legal side that only the
operator can own. Work through it **before go-live** and review it yearly.

> Not legal advice. A licensed daycare or school should have its privacy
> practices reviewed by counsel familiar with its jurisdiction.

## 1. Know your regime

- [ ] Identify which apply: **PIPEDA** (Canada, private), provincial rules
      (e.g. Ontario **CCEYA** for licensed child care, **FIPPA/MFIPPA** for a
      public board, **PHIPA** for health information), or **FERPA** / **COPPA**
      / a state student-privacy law (US).
- [ ] Name a **privacy contact** (person + email) and put it in your intake
      forms and on your site.

## 2. Data you collect

- [ ] For every field Campus captures, confirm you have a **stated purpose**
      and are not collecting more than you need (Campus lists purpose +
      retention per field in `DATA_MODEL.md`).
- [ ] Set **retention windows** in Campus (`RETENTION_PAST_STUDENT_DAYS` and
      the per-record overrides) to match your legal minimums and your policy.
- [ ] Turn on the scheduled **retention job** and confirm it runs.

## 3. Consent

- [ ] Configure the consent kinds you use (photo/media, field trips, emergency
      medical, information sharing, third-party programs) with the wording your
      counsel approves; Campus versions and timestamps each.
- [ ] Confirm the parent portal shows current consents and lets a guardian
      review / withdraw.

## 4. Access

- [ ] Decide **who gets the health-data role** — keep it to the minimum staff
      who need allergy/medication info to keep a child safe.
- [ ] Every staff account uses **MFA** (Campus enforces this for staff roles).
- [ ] Front-desk / casual staff get `FRONT_DESK`, not `ADMIN`.
- [ ] The **break-glass Django admin** is used only for recovery; its IP
      allow-list is set to your admin machine(s).
- [ ] Review the **audit log** on a schedule — unexpected reads of a child's
      record are the thing to look for.

## 5. Requests &amp; incidents

- [ ] Document your process for a **records access request** — Campus has a
      one-click "export everything about this child"; decide who runs it and
      how identity is verified.
- [ ] Document your process for a **correction / erasure request** — Campus has
      an "erase this person" admin action; decide who approves it and how
      legal-hold is flagged.
- [ ] Have a **breach response** plan: who is called, within what time, and
      what your regulator requires you to report.

## 6. Infrastructure (with your IT)

- [ ] The Campus server has **full-disk encryption** on.
- [ ] **Backups** run on a schedule, are encrypted, and are stored off the
      Campus box. A **restore has been tested**.
- [ ] Campus is **not reachable from the internet** (LAN only, or behind your
      VPN).
- [ ] The server's OS is patched; only trusted staff have local admin.
- [ ] When the server is retired, its disks are wiped or destroyed.
