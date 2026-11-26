# Validation scope

Release 0.2.0 has 195 video runtime files, identified by SHA-256
`9952b11c019aba4adf4144b73ab2fa02f8d470a742bd29fe56ce53c1f82ba847`.

Native batch editing was verified on Windows Blender 5.3.0, build `02f0899d78e3`. The checks cover split, insertion and removal, source positions, group and batch rollback, resource verification, and independent reopening. The release installer `video_editing_workflow_addon-0.2.0.zip` is the verified 48,579-byte archive with SHA-256 `7d7d434f3891e87ccdf0577fc017dbcec0a1c3084c59705435672945ec652940`. Its twelve source members match this checkout byte for byte. The deterministic local build also includes the add-on license file and produces a different ZIP with the same plugin sources.

`PUBLICATION.json` records the full explicit release inventory including supporting addons, schemas, helper adaptations and documents. The video runtime identity covers a smaller set; it is not a hash of the complete distribution. All source ZIP members must match the staged Git tree and inventory.

The public template compiler differs from its local source only in root resolution (`BLENDERCTL_ROOT` or the source root). Media/proxy helpers use the same relocation convention; the SRT helper takes `--root`. Public docs exclude private project state. The four preset JSON files and catalog retain their original bytes and hashes.

Reproducible packaging uses ZIP_STORED with fixed member timestamps and permissions. Every build reads the archive back and compares each member. `verify_release.py` checks explicit hashes, runtime identity, syntax, skill links and targeted privacy patterns. These finite scans do not certify behavior or guarantee absence of every possible secret.

Host tests exercise actual CLI subprocesses, template compiler constraints and skill packaging. The historical 0.1.3 native smoke summary is in `RELEASE-VALIDATION.json`. The smoke runs a serial create/output followed by cold inspection, eight 160×90 SDR main frames and eight per-shot frames, exact decoded pixels at the cut, and unchanged source SHA. The optional native smoke requires an existing Pillow installation and Blender. CI runs host checks.

Earlier local validation included 35 compiler tests, seven small public template cases, separate movie/portrait input cases and decoded image/audio checks. Those historical checks are not a new full regression of this archive. This publication does not requalify every material, geometry, lighting, compositing or CLI adapter. Matching version numbers alone do not guarantee matching implementation identities between independently frozen specialty releases.

No 4K/HDR stress test, HDR display review, arbitrary foreign VSE, advanced audio, complex acting or long-form production qualification is claimed. Do not treat registration, static checks or a generated technical clip as artistic acceptance.

Publication revision r1 resolves Windows 8.3 TEMP aliases in the pure test fixture before comparing resource descriptors. The compiler already normalizes these paths; no production behavior or native qualification changed.
