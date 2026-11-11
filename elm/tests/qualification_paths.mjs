// Explicit external prerequisites for the optional host/browser qualification lanes.
// This module never selects an installed user profile or scans for credentials.
import path from 'node:path';
import os from 'node:os';
import {existsSync,mkdirSync} from 'node:fs';
export function requireQualificationPath(name) {
  const value=process.env[name];
  if(!value||!path.isAbsolute(value)||!existsSync(value)) {
    throw Error(`Set ${name} to an existing absolute path; see tests/QUALIFICATION_SETUP.md`);
  }
  return path.resolve(value).replaceAll('\\','/');
}
export function qualificationScratch(suite) {
  if(!/^[a-z0-9-]+$/.test(suite))throw Error('Invalid qualification suite name');
  const base=process.env.ELM_TEST_SCRATCH_ROOT||path.join(os.tmpdir(),'elm-source-qualification');
  if(!path.isAbsolute(base))throw Error('ELM_TEST_SCRATCH_ROOT must be absolute');
  const directory=path.join(base,suite);
  mkdirSync(directory,{recursive:true});
  return directory+path.sep;
}
export function qualificationPython() {
  return process.env.ELM_TEST_PYTHON?requireQualificationPath('ELM_TEST_PYTHON'):(process.platform==='win32'?'python':'python3');
}
