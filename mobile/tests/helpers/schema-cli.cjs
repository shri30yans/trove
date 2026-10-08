const { createLoader } = require('./typescript-loader.cjs');
const [file, name] = process.argv.slice(2);
const schema = createLoader()(file)[name];
let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  console.log(JSON.stringify({ valid: schema.safeParse(JSON.parse(input)).success, labels: schema.options ?? null }));
});
