---
name: Secret Leak Incident
about: Report and track response to an accidentally exposed secret or credential.
title: 'Incident: Secret Leak - [Credential Type]'
labels: security, incident
assignees: ''
---

## Description of Incident

> [!WARNING]
> NEVER include the actual exposed secret value, hash, or credentials in this issue.

**Credential Type:** (e.g., AWS Access Key, Stripe API Key, database password)
**Exposed Location:** (e.g., commit hash, file path and line number, branch name)
**Exposure Duration:** (approximate time from commit to rotation)

## Containment & Rotation Checklist

- [ ] **Step 1: Rotate the Credential**
  - [ ] Generate a new credential/key at the provider.
  - [ ] Update all environment variables, deployed configs, and developer machines.
  - [ ] Revoke/deactivate the old credential at the provider.
- [ ] **Step 2: Scrape Verification**
  - [ ] Confirm the old credential can no longer be used to access services.
- [ ] **Step 3: Internal Notification**
  - [ ] Identify and notify affected teams/systems.
  - [ ] List any notified services or users:
- [ ] **Step 4: History Cleaning (Discretionary)**
  - [ ] Determine if a history scrub (force-push/BFG) is required.
  - [ ] Actions taken:

## Verification and Close

- **Verified by:**
- **Verification steps performed:**
