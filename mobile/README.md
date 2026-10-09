# Trove mobile client

Expo React Native client for the Trove API. The UI follows the supplied OpenDesign export in `../design-reference/`. Screens use Expo Router under `src/app/`.

## Configure

Copy `.env.example` to `.env` and set `EXPO_PUBLIC_API_URL` to an address the device can reach. Production Expo builds use the tracked, non-secret `.env.production` value `https://api.trove.zyphrlabs.com`. All media transfers and authentication go through the authenticated Trove API. Local and deployed APIs verify Supabase Auth sessions with their configured issuer and JWKS. The app has no development sign-in bypass; use a synthetic user from the dedicated development Supabase project for device testing.

## Start

```sh
npm install
npx expo prebuild
npm run ios
# or
npm run android
```

Use `npm run start` to run Metro against an installed development client using the default `.env`. Use `npm run start:prod` to target the production cloud API (`https://api.trove.zyphrlabs.com`) or `npm run start:local` to target your local API (`http://localhost:4000`). Standard Expo Go cannot run this application because Trove uses native share extension hooks (`expo-share-intent`) and keyboard controller drivers (`react-native-keyboard-controller`); always use a development build (`npm run ios` or `npm run android`). The share extension accepts text/URLs and shared media/files from other applications. Offline notes, links, and file captures are kept in the app's document storage and sync when connectivity returns.

Run `npm run typecheck` and `npm run lint` to check the TypeScript client. `npm run prebuild` regenerates the native iOS and Android projects from `app.json`.

See [sync-design.md](docs/sync-design.md) for the save-delivery contract, status derivation, recovery behavior, and infrastructure limits. Run `npm test` for the sync regression tests.

## Password reset email setup

The password recovery endpoint redirects email links to `trove://reset-password`. Add that exact URI to the configured Supabase project's Auth redirect URL allow list. The app already registers the `trove` scheme. Reset links are delivered only after the project's email provider and password auth are configured.

Before delivery run `npm run check`. Before release run `npm run verify:ios` and complete screenshot review and the release checklist in [ui-verification.md](docs/ui-verification.md). Missing native verification blocks release.
