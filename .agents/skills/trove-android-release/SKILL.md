---
name: trove-android-release
description: Build and prepare signed Trove Android App Bundles for Google Play, using the repeatable local build helper or the documented manual workflow.
---

# Trove Android release

Use this skill when building a Trove Android AAB, preparing a Play Console upload, or documenting the manual release steps. Read the repository `AGENTS.md` and `mobile/AGENTS.md` first.

## Fast local build

Use the helper for a local signed bundle when the upload keystore is available:

```sh
python3 .agents/skills/trove-android-release/scripts/build_android_bundle.py
```

It runs Expo prebuild for Android, builds the production AAB, verifies its signature against the configured upload key, and copies it to `artifacts/`. It refuses to overwrite an existing artifact. The helper reads the private credential file named by `TROVE_UPLOAD_CREDENTIALS_FILE`, or the current macOS Trove credential file if present. It can also read the four `TROVE_UPLOAD_*` environment variables described in the reference. It never prints password values.

Use the EAS cloud build flow from `mobile/AGENTS.md` when EAS is configured and authenticated. Use the local helper when the user wants a local AAB or EAS is unavailable. Do not create a replacement upload key for an app that already has a Play Console listing; use that listing's key.

## Manual workflow

Read [references/manual-play-release.md](references/manual-play-release.md) when the user asks to build through Android Studio/Gradle, needs Play Console steps, or wants to provision/recover signing credentials.

## Release checks

- Confirm the application ID in `mobile/app.json` is available for the intended Play Console entry before the first upload. Play requires each update to use a higher `android.versionCode`. Never change the package ID after creating the listing.
- The current mobile release instructions require `npm run verify:ios` and screenshot review before release. A successful AAB build does not satisfy the app's native UI release gate. Report any concrete simulator/tooling blocker.
- Treat the AAB as an upload candidate until Play Console accepts it. The console still checks app signing, package ownership, target SDK, declarations, store listing, and track requirements.
- Keep the upload keystore and credentials outside Git and backups secure. Never put them in the app, command output, `.env` committed to Git, or the AAB artifact folder.
- Do not upload, publish, or change a Play track unless the user explicitly requests that action.
