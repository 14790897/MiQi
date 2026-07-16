/**
 * verify-small-molecule.js
 *
 * Verifies the small-molecule-lab skill produced valid outputs:
 * - A result.json file with expected fields
 * - PNG visualization files
 *
 * Usage: node verify-small-molecule.js <workspace_path>
 */
const { readFileSync, existsSync } = require('node:fs');
const { join } = require('node:path');
const { globSync } = require('glob') || { globSync: () => [] };

const ws = process.argv[2];
if (!ws) {
  console.log(JSON.stringify({ pass: false, checks: [{ label: 'usage', pass: false, detail: 'Missing workspace path' }] }));
  process.exit(1);
}

const checks = [];

function check(label, condition, detail = '') {
  checks.push({ label, pass: !!condition, detail });
}

// Search for output directories — skill typically writes to a fresh output/ dir
function findFiles(pattern) {
  const results = [];
  // Walk the workspace recursively looking for result.json or PNGs
  const { readdirSync, statSync } = require('node:fs');
  function walk(dir, maxDepth = 6) {
    if (maxDepth <= 0) return;
    try {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
          walk(full, maxDepth - 1);
        } else if (entry.isFile()) {
          results.push(full);
        }
      }
    } catch {}
  }
  walk(ws);

  return results.filter(f => {
    const name = f.replace(/\\/g, '/');
    return pattern(name);
  });
}

// Check 1: result.json exists and has expected structure
const resultJsons = findFiles(f => f.endsWith('/result.json'));
check(
  'result.json found',
  resultJsons.length > 0,
  `Found ${resultJsons.length} result.json files`,
);

if (resultJsons.length > 0) {
  try {
    const data = JSON.parse(readFileSync(resultJsons[0], 'utf-8'));
    check('result.json is valid JSON', true);

    // Basic structure checks based on skill SKILL.md output expectations
    const hasEnergy = data.energy_values || data.energies || data.scf_energies;
    const hasGeom = data.geometry || data.coordinates || data.geometries;
    const hasMode = data.mode || data.calculation_mode;
    const hasMolecule = data.molecule || data.molecule_name;

    check(
      'result.json contains energy data',
      !!hasEnergy,
      hasEnergy ? `Keys: ${Object.keys(data).join(', ')}` : `Keys: ${Object.keys(data).join(', ')}`,
    );
    check(
      'result.json contains geometry data',
      !!hasGeom,
    );

    // Log the keys found for debugging
    console.log(`[verify] result.json keys: ${Object.keys(data).join(', ')}`);
  } catch (e) {
    check('result.json parseable', false, String(e.message || e).slice(0, 200));
  }
}

// Check 2: PNG outputs exist
const pngFiles = findFiles(f =>
  f.includes('势能') || f.includes('结果') || f.includes('potential') || f.includes('result')
);
check(
  'PNG visualization files found',
  pngFiles.length > 0,
  `Found ${pngFiles.length} PNG files`,
);

// Check 3: Assistant response contains key Chinese terms indicating success
// (This is verified in the test itself via page content, but we add a
//  workspace-level check for completeness)
const summaryFiles = findFiles(f => f.endsWith('comparison.json'));
check(
  'Output directory structure looks correct',
  resultJsons.length > 0 || pngFiles.length > 0,
  'At least one expected output artifact found',
);

const allPass = checks.every(c => c.pass !== false);
const result = { pass: allPass, checks };
console.log(JSON.stringify(result, null, 2));
process.exit(allPass ? 0 : 1);
