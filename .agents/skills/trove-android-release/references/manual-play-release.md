# Manual Trove Android release

Use this when the user wants to inspect or perform each release step manually. This guide prepares an AAB; Play Console submission is a separate user-directed action.

## Before building

1. Read the repository `AGENTS.md`, `mobile/AGENTS.md`, and `mobile/docs/ui-verification.md`.
2. Check the Android package ID in `mobile/app.json` before creating the Play listing. It is currently `com.trove.memory`. Check availability in Play Console and keep it unchanged after creating the listing. The iOS bundle ID is separate.
3. Set `expo.android.versionCode` to a positive integer greater than the last version accepted by Play. Increase `expo.version` when appropriate. A new listing can start at version code `1` if no bundle has been accepted for that listing.
4. Run `npm run check` in `mobile/`. Before treating the app as release-ready, run `npm run verify:ios` and review the produced screenshots as the repository release rules require. An Android bundle build does not pass that gate.
5. Use the upload key already associated with the Play listing. The current local key is at `~/Library/Application Support/TroveApp/play-upload/trove-upload.jks`; its private credentials file is beside it. Keep both backed up securely and outside the repository. Create a new upload key only for a genuinely new listing or a Play Console key reset.

## Android Studio build

1. From `mobile/`, generate the native Android project from the Expo config:

   ```sh
   npx expo prebuild --platform android --no-install
   ```

2. Open `mobile/android` in Android Studio and wait for Gradle sync.
3. Select **Build → Generate Signed Bundle / APK… → Android App Bundle**.
4. Select the existing upload keystore and alias. Enter the store and key passwords from the private credential store. Do not create a replacement key for an existing Play listing.
5. Select the `release` build variant and finish. Android Studio reports the signed `.aab` output path when it completes.
6. Verify the output with `jarsigner -verify <path-to-aab>` and inspect its certificate with `keytool -printcert -jarfile <path-to-aab>`. Confirm the certificate fingerprint matches the upload key before using the bundle.
7. Copy the verified bundle to `artifacts/Trove-<version>-<versionCode>.aab`. Keep the release artifact separate from source and signing files.

## Play Console upload

1. Open the existing Trove app in Play Console. For a new app, confirm the package ID is available before creating the listing.
2. Start with the internal testing track and upload the signed AAB.
3. Complete any blocking Play Console declarations, including app access, ads, content rating, data safety, privacy policy, and store listing details.
4. Review Play's bundle validation and warnings. Resolve package, signing, target SDK, version code, or policy errors in the project, then rebuild with the same upload key and a higher version code.
5. Leave rollout or production publication for the user's explicit instruction. Uploading an AAB does not publish it.

## Local Gradle command

The skill helper wraps Expo prebuild, signed Gradle bundle generation, signature matching, and copy to `artifacts/`:

```sh
python3 .agents/skills/trove-android-release/scripts/build_android_bundle.py
```

When EAS is configured and authenticated, follow `mobile/AGENTS.md`'s EAS workflow instead. The local helper is for local artifacts and for environments where EAS cannot build.
