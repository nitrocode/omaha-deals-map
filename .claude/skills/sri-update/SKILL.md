---
name: sri-update
description: Compute the correct Subresource Integrity (SRI) hash for a CDN URL and (optionally) splice it into site/index.html. Use whenever you bump a CDN library version, add a new <link>/<script> with integrity=, or are about to write any SRI attribute. This skill exists because we shipped a fabricated-hash bug once.
---

# sri-update

Compute the correct SRI hash for a remote resource. Never invent these values.

Usage:

- `/sri-update <url>`, computes the hash and prints it
- `/sri-update <url> --apply`, computes the hash AND updates site/index.html in
  place if the URL is already referenced there (only the `integrity=` value is
  replaced; the URL and surrounding markup stay untouched)

## What to do

1. **Validate the URL.** Must be `https://...`. If not, refuse and explain
   that SRI is only meaningful over TLS.

2. **Compute sha384, sha256, and (for cross-verify) cdnjs**.

   ```bash
   curl -sL "<URL>" | openssl dgst -sha384 -binary | openssl base64 -A
   curl -sL "<URL>" | openssl dgst -sha256 -binary | openssl base64 -A
   ```

   If the URL is an unpkg URL of the form
   `https://unpkg.com/<pkg>@<ver>/<path>`, also fetch the cdnjs mirror
   `https://cdnjs.cloudflare.com/ajax/libs/<pkg>/<ver>/<path>` and verify
   sha384 matches. If they differ, STOP and surface the mismatch, since one
   of the mirrors may be serving compromised content.

3. **Report the canonical hash**:

   > URL: <URL>
   > size: <bytes>
   > sha384: <base64>
   > sha256: <base64>
   > (cdnjs cross-check: matches | differs | n/a)
   >
   > Use this `<link>`/`<script>` form:
   >
   > integrity="sha384-<base64>" crossorigin=""

4. **If `--apply`**: find the existing tag in `site/index.html` that references
   this URL and rewrite only its `integrity=` attribute to the new sha384 value.
   Leave the URL, `crossorigin`, and surrounding markup byte-identical.

   After applying, run `python scripts/check_sri.py site/index.html`. It must
   return `OK` with exit 0. If it fails, restore the file from git and surface
   the error.

5. **Never** propose a hash you computed by guessing or by adapting one from
   a different file or version. If `curl` failed or returned 0 bytes, stop
   and tell the user. CLAUDE.md documents why.

## Output format

Print the result in a single Markdown block so the user can copy-paste:

```
integrity="sha384-<base64>" crossorigin=""
```

## When to invoke yourself (model-invocation)

Anytime you would write or modify an `integrity=` attribute in HTML for a
remote subresource. The pre-commit `verify-sri` hook will block the commit
anyway, but invoking this skill catches it earlier and shows the right hash.
