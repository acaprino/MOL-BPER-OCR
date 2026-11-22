import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const requireRuntime = createRequire('C:/Users/alfio/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const { Workbook } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const workbook = Workbook.create();
workbook.worksheets.add('Sheet1');
console.log(workbook.help('*', { search: 'hyperlink|Hyperlink', include: 'index,examples,notes', maxChars: 3500 }).ndjson);
process.exit(0);
