# Shared mobile layout and design

Theme tokens live in `src/theme.ts`; shared components own rendering and accessibility.

Use `ScreenFrame` for bounded content and a fixed footer in normal layout. Use `FormScreen` for scrolling forms. Both share safe areas and header insets. Do not overlay actions and compensate with guessed padding.

One root `KeyboardProvider` supplies react-native-keyboard-controller. Only `screen-frame.tsx` imports its keyboard layout components. ScreenFrame uses KeyboardAvoidingView with automaticOffset; FormScreen uses KeyboardAwareScrollView without a second avoiding wrapper. The library owns tracking, animation and platform adjustment. Screens must not add keyboard listeners, measurements or offsets.

Keyboard entry remains owned by `useKeyboardOnScreenFocus`. Headers use ScreenHeader, fields use TextField, actions use Button, menus and confirmations use ActionSheet, and failures use notices.

Run `npm run check`. Static checks do not establish native visual correctness. Follow `docs/ui-verification.md` before release and review Capture, Search, Space creation and Memory details on native devices.


The New memory composer grows to fill the available screen body; its editor flexes above the action row while the shared frame handles keyboard resizing. Glyph size is independent of the shared touch target. System background, status bar and Android navigation styling are owned by the root layout, including modal screens. Android contrast configuration is a native plugin setting and requires a new native build; Expo Go retains its own host configuration.

Space creation uses FormScreen, with a name and an optional description (500 characters), and saves through the existing API. Default capture destinations are labelled DEFAULT SPACE, rather than QUICK SAVE. Voice recording/browse choices are absent; previously saved or imported audio remains readable as an audio file.
