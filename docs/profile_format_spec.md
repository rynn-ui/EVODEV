# EvoDev Portable Experience Profile (.vxp) Specification

## 1. Specification Overview
The `.vxp` format (**Verified Experience Profile**) is an open, portable, self-contained archive standard designed to package accumulated software engineering lessons, strategy statistics, user preferences, and empirical benchmarks into a single distributable artifact.

A `.vxp` archive is transportable across machines, operating systems, and developer environments. It does not require a running server to inspect or validate.

---

## 2. Archive Structure

A `.vxp` package is a standard ZIP container (optionally encrypted with AES-256-GCM) containing exclusively structured JSON data and integrity digests:

```
<profile-name>.vxp
├── manifest.json       # Profile metadata, UUID, schema version, checksums, author
├── lessons.json        # Array of verified, generalized lessons with provenance
├── strategies.json     # Empirical success/failure/regression outcome statistics
├── preferences.json    # User style rules, test runner choices, scope overrides
├── benchmarks.json     # Empirical evaluation scores across benchmark suites
└── integrity.sha256    # SHA-256 cryptographic digest of uncompressed payload
```

No executable binaries, shell scripts, Python `.py` or `.pyc` files, or binary shared objects are permitted in `.vxp` archives.

---

## 3. Manifest Schema (`manifest.json`)

```json
{
  "profile_id": "c7a8b411-9a73-4e89-b883-93f54d193d50",
  "name": "AndroidExpert.vxp",
  "version": "1.2.0",
  "description": "Android Compose and Gradle enterprise lessons",
  "author": "EvoDev Agent",
  "schema_version": "1.0.0",
  "domains": ["mobile"],
  "technologies": ["android", "kotlin", "compose", "gradle"],
  "created_at": "2026-10-20T10:00:00Z",
  "updated_at": "2026-10-22T14:30:00Z",
  "stats": {
    "total_lessons": 14,
    "total_strategies": 6,
    "total_experiences": 42,
    "verified_lessons_count": 14,
    "total_benchmarks": 3
  },
  "payload_checksum": "a3f5b7c...64charHex"
}
```

---

## 4. Integrity and Security Controls

### Integrity Checksum
Before serialization, a canonical SHA-256 hash is computed over the combined payload streams (`lessons.json`, `strategies.json`, `preferences.json`, `benchmarks.json`). This hash is saved in `integrity.sha256` and stored in `manifest.payload_checksum`. Upon import, the hash is recomputed and compared before accepting data.

### Zip-Slip & Path Traversal Guards
- All member paths are inspected before extraction.
- Directory traversal sequences (`..`), leading slashes (`/`, `\`), and drive letters (`C:`) are prohibited.
- Extraction resolves only to canonical target subpaths inside a controlled sandbox.

### Decompression Limits (Zip-Bomb Defense)
- Maximum uncompressed size: **50 MB**
- Maximum single entry size: **20 MB**
- Maximum file entries: **20 files**

### Optional Authenticated Encryption
When encryption is enabled during export:
1. A 256-bit key is derived from the user password using **PBKDF2-HMAC-SHA256** with a 16-byte random salt and 100,000 iterations.
2. The entire archive stream is encrypted with **AES-256-GCM** using a 12-byte random nonce.
3. The format prepends: `[16-byte Salt] + [12-byte Nonce] + [Ciphertext + 16-byte GCM Tag]`.
4. Tampering or incorrect password triggers authentication failure during decryption before parsing.
