const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, mocks = {}) {
  const module = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, require: (name) => mocks[name] ?? require(name) });
  return module.exports;
}
const theme = load('src/theme.ts');
const themeProvider = {
  useTheme: () => ({ colors: theme.themes.light.colors }),
  useThemedStyles: (make) => make(theme.themes.light.colors),
};
const mocks = {
  'react-native': { View: 'View', ScrollView: 'ScrollView', Pressable: 'Pressable', Text: 'Text', ActivityIndicator: 'ActivityIndicator', StyleSheet: { create: (styles) => styles } },
  '@expo/vector-icons': { Ionicons: 'Ionicons' },
  '../theme': theme,
  '../../theme': theme,
  '../providers/theme-provider': themeProvider,
  '../../providers/theme-provider': themeProvider,
};
function style(element) {
  return Object.assign({}, ...element.props.style({ pressed: false }).flat(Infinity).filter(Boolean));
}
module.exports = { load: (file) => load(file, mocks), style };
