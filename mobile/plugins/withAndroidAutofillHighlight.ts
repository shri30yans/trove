import { withAndroidStyles, type ConfigPlugin } from '@expo/config-plugins';

/**
 * Android paints an opaque yellow block over text an autofill service inserted.
 * Trove owns field highlighting (focus border + selectionColor), so the native
 * overlay is made transparent on every generated app theme. Autofill itself and
 * the credential picker are untouched.
 */
const withAndroidAutofillHighlight: ConfigPlugin = (config) =>
  withAndroidStyles(config, (config) => {
    const styles = config.modResults.resources?.style ?? [];
    if (!styles.length) throw new Error('Android styles.xml contained no themes; cannot disable the native autofill highlight.');
    for (const style of styles) {
      style.item ??= [];
      const existing = style.item.find((item) => item.$?.name === 'android:autofilledHighlight');
      if (existing) existing._ = '@android:color/transparent';
      else style.item.push({ $: { name: 'android:autofilledHighlight' }, _: '@android:color/transparent' });
    }
    return config;
  });

export default withAndroidAutofillHighlight;
