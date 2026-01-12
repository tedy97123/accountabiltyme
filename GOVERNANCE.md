# Governance

## Statement of Intent

AccountabilityMe is **open infrastructure**.

The specification, reference implementation, and verification tools are released under the Apache 2.0 license. This means:

- **Anyone** can read, use, and implement the spec
- **Anyone** can run their own ledger
- **Anyone** can build verifiers
- **Anyone** can create compatible tools
- **No paywall** on verification

This is intentional and permanent.

## Core Principles

### 1. The Spec is the Standard

The protocol is defined by `spec/v1.md`, not by any particular implementation. If the reference implementation disagrees with the spec, the spec wins.

New implementations should pass the same verification tests as the reference implementation.

### 2. Verification Must Be Free

Independent verification of claim bundles must never require:
- A subscription
- An API key
- Access to a specific server
- Permission from any party

The verification algorithm is public. The bundle format is public. Anyone can verify.

### 3. No Gatekeeping on Claims

The claim format can be used by anyone to record any public claim. The reference implementation does not have a monopoly on "official" claims.

Different organizations may run their own ledgers with their own editorial policies. Bundles from any compliant ledger should be verifiable by any compliant verifier.

### 4. Backward Compatibility

Breaking changes to the canonicalization algorithm, hash format, or bundle structure require a new spec version.

Old bundles must remain verifiable forever. This is non-negotiable—it's the foundation of the system's credibility.

### 5. Spec Immutability

**Published spec versions are immutable.**

Once a spec version (e.g., `spec/v1.md`) is published:
- It **cannot** be edited, clarified, or "fixed"
- Corrections require a new version (`spec/v1.1.md` or `spec/v2.md`)
- The original version remains the authoritative reference for bundles created under it

This governance document may evolve. The spec cannot (without versioning).

**Rationale**: If specs could be silently edited, old bundles might become "invalid" under the "same" spec. That breaks the entire trust model.

### 5. Transparency Over Control

If this project grows beyond a single maintainer:
- Governance decisions will be documented publicly
- Editorial policies will be explicit
- Technical changes will be discussed in the open

## Current Governance

**Maintainer**: This project currently has a single maintainer.

Until there is broader adoption, governance is simple:
- The maintainer sets technical direction
- The maintainer defines editorial policy for the reference instance
- The maintainer accepts or rejects contributions

This will evolve as the project matures.

## Contributing

Contributions are welcome. Before making major changes:

1. Open an issue describing the proposed change
2. Wait for discussion before implementing
3. Ensure all tests pass
4. Ensure the change is backward-compatible (or clearly documents why it isn't)

For spec changes:
- Propose changes as a new version (e.g., `spec/v2.md`)
- Never modify published spec versions
- Include migration guidance

## Future Governance

As adoption grows, governance may evolve toward:

- **Technical Steering Committee**: For spec changes
- **Editorial Board**: For reference instance policies
- **Foundation**: For long-term stewardship

These structures will be established when needed—not before. Premature institutionalization creates overhead without benefit.

## Non-Goals

This project will **not**:

- Become a commercial product that locks users in
- Add features that require centralized verification
- Accept changes that break backward compatibility without versioning
- Prioritize any political orientation in editorial decisions

## Contact

For governance questions: open an issue on the repository.

## Security Disclosure

If you discover a security vulnerability that could affect the integrity of the ledger, bundle verification, or cryptographic guarantees:

**Do NOT open a public issue.**

Instead:
1. Email: `security@accountabilityme.org` (placeholder—update when domain is established)
2. Include: description, reproduction steps, potential impact
3. Allow 90 days for response before public disclosure

We take security seriously because the system's value depends on cryptographic trust. Responsible disclosure will be acknowledged in release notes (with permission).

**Future**: When the project matures, maintainer PGP key fingerprints will be published here for verified communication.

---

*This document may be updated. Changes will be tracked in version control.*

