const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = '/home/huangpan/github_repo/langflow';
const frontend = path.join(root, 'src/frontend');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const output = path.join(root, 'deploy/business/evidence/results-evidence-20261015');
const files = [
  'src/pages/BusinessPage/ResultFields.tsx',
  'src/pages/BusinessPage/ResultEvidenceDialog.tsx',
  'src/pages/BusinessPage/BusinessResultEvidence.tsx',
  'src/pages/BusinessPage/ResultStorage.tsx',
  'src/pages/BusinessPage/BusinessResults.tsx',
  'src/pages/BusinessPage/ResultsConfiguration.tsx',
  'src/controllers/API/queries/business/index.ts',
  'src/pages/FlowPage/components/SelectionMenuComponent/index.tsx',
].map(p => path.join(frontend, p));
const configFile = ts.readConfigFile(path.join(frontend, 'tsconfig.json'), ts.sys.readFile);
const config = ts.parseJsonConfigFileContent(configFile.config, ts.sys, frontend);
const program = ts.createProgram([...files, ...config.fileNames.filter(p => p.endsWith('.d.ts'))], config.options);
const diagnostics = [...config.errors, ...program.getGlobalDiagnostics(), ...files.flatMap(file => {
  const source = program.getSourceFile(file);
  return [...program.getSyntacticDiagnostics(source), ...program.getSemanticDiagnostics(source)];
})];
const formatter = {getCanonicalFileName: f => f, getCurrentDirectory: () => frontend, getNewLine: () => '\n'};
const text = ts.formatDiagnostics(diagnostics, formatter);
const report = {scope: 'Changed production files; real tsconfig and imports; no type stubs', exit_code: diagnostics.length ? 1 : 0, diagnostics: text, files: Object.fromEntries(files.map(file => [path.relative(root, file), crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]))};
fs.writeFileSync(path.join(output, 'typecheck-focused.json'), JSON.stringify(report, null, 2) + '\n');
console.log(text || `Focused semantic type check passed: ${files.length} production files.`);
process.exitCode = report.exit_code;
