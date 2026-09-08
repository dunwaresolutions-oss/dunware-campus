# Remote access & your data

*A plain-English answer to: "if we let parents and staff reach Campus from
home, where does our data actually go?"*

## The short version

Campus runs on **one computer inside your building**. The database, every
uploaded document, and every backup live **only on that computer**. That does
not change when you turn on remote access. No outside company ever *stores* a
student record, a report card, a health note, or an attendance mark.

What remote access changes is the **path a connection takes** to reach that
computer from outside — not where anything is kept.

Remote access is **optional**, set up separately by a technician, and can be
**switched off at any time**, which returns Campus to a state where nothing
leaves the building at all.

## The three ways to do it

| | What travels outside | Who can read it in transit | Best for |
|---|---|---|---|
| **Cloudflare Tunnel** | Encrypted web traffic, via Cloudflare's network | Cloudflare's edge briefly decrypts each request to check the sign-in and re-encrypts it (sub-second, not stored) | Parents / anyone — nothing to install |
| **WireGuard VPN** | Encrypted traffic only Cloudflare-style middle layer | **No one** — it stays encrypted end to end; the school's computer is the only thing that can read it | Staff — needs an app + a config per device |
| **Plain gateway** | Encrypted web traffic, direct to the school | **No one** but the school's own computer (it holds the certificate) | Schools that want their own domain and no third party at all |

All three keep the database, files and backups on-premises. They differ only in
**how much a third party can see the traffic while it is moving**.

## Cloudflare Tunnel — the detail, because it's the one people ask about

When Cloudflare Tunnel is enabled:

- A small outbound-only program on the school's computer keeps a connection open
  to Cloudflare. **Nothing on the school network is exposed to the internet** —
  there is no open port for an attacker to find.
- A visitor goes to e.g. `portal.yourschool.edu.bs`. Cloudflare answers, checks
  they are allowed in (**Cloudflare Access** — email code, or your Google /
  Microsoft sign-in), and forwards the request down the tunnel to the school.
- To run that check, Cloudflare's edge server **decrypts the request, then
  re-encrypts it** for the last hop. So for the fraction of a second it is
  passing through, the content is technically readable by Cloudflare.
- Cloudflare **does not keep** the contents of pages or records. It **does keep
  connection logs**: timestamps, IP addresses, which hostname, and the identity
  of the person who signed in.
- Cloudflare's edge is a global network; for a Canadian or Caribbean school this
  means some traffic metadata is processed on infrastructure outside the
  country. **Data at rest is unaffected — it never leaves the school.**

If even that brief in-transit visibility is unacceptable, use **WireGuard** or
the **plain gateway** instead: in both, the encryption is only undone on the
school's own computer.

## What Campus does to protect a remote connection

- **Cloudflare Access (or your VPN) is the first wall.** A request is checked
  for a valid identity *before* it reaches Campus at all.
- **Campus's own login is the second wall** — every remote user still signs in
  to Campus, and staff still complete MFA.
- **The real visitor's address is preserved**, so the lock-out-after-5-failures
  protection and the audit log record the actual person, not the tunnel.
- **The `/admin` engineering console stays LAN-only** — it is not reachable
  through remote access, by any route.
- **Roles still apply.** A parent signing in from home sees exactly what a
  parent sees in the building: their own child, nothing else.

## Turning it off

A technician runs one command on the school's computer
(`deploy\remote-setup.ps1 -Mode Off`). The tunnel/VPN stops, the setting is
cleared, Campus restarts LAN-only. **Nothing is removed from the database.**

## The one sentence that changes in our materials

Before: *"Your data never leaves the building."*
After: *"Your data is never **stored** anywhere but the building. If you choose
to enable remote access, encrypted connections are **routed** through a
third-party network to reach it — and you can turn that off whenever you want."*
