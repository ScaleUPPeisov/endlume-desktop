# ENDLUME Remote Release Pipeline

- Source repository is private.
- GitHub Actions builds on macOS ARM64.
- Tauri updater artifacts are signed with `TAURI_SIGNING_PRIVATE_KEY` stored as a GitHub Actions Secret.
- The private key is never committed to Git.
- Release commits use the prefix `release:` and are pushed to the `release` branch.
- The workflow uploads `.app.tar.gz`, `.sig`, and `release.json` as a private Actions artifact.
- ChatGPT retrieves that artifact and publishes it to ENDLUME's public update channel on Vercel.
