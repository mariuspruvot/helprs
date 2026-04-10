// Refractor v4 uses a named `refractor` export + explicit language registration.
// Registering only the common demo/user languages keeps the bundle tight
// (Task 1.3). Unknown extensions fall back to plain text at the call site.

import { refractor } from 'refractor/lib/core.js'

import go from 'refractor/lang/go.js'
import javascript from 'refractor/lang/javascript.js'
import json from 'refractor/lang/json.js'
import jsx from 'refractor/lang/jsx.js'
import markdown from 'refractor/lang/markdown.js'
import python from 'refractor/lang/python.js'
import rust from 'refractor/lang/rust.js'
import tsx from 'refractor/lang/tsx.js'
import typescript from 'refractor/lang/typescript.js'
import yaml from 'refractor/lang/yaml.js'

refractor.register(go)
refractor.register(javascript)
refractor.register(json)
refractor.register(jsx)
refractor.register(markdown)
refractor.register(python)
refractor.register(rust)
refractor.register(tsx)
refractor.register(typescript)
refractor.register(yaml)

const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  ts: 'typescript',
  mts: 'typescript',
  cts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  jsx: 'jsx',
  py: 'python',
  pyi: 'python',
  go: 'go',
  rs: 'rust',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  md: 'markdown',
  markdown: 'markdown',
}

export function languageFromPath(path: string | undefined): string | undefined {
  if (!path) return undefined
  const basename = path.split('/').pop() ?? ''
  const dotIndex = basename.lastIndexOf('.')
  if (dotIndex < 0 || dotIndex === basename.length - 1) return undefined
  const ext = basename.slice(dotIndex + 1).toLowerCase()
  return EXTENSION_TO_LANGUAGE[ext]
}

// Type-cast escape hatch — react-diff-view 3.x still targets refractor v2's
// type shape (`import type { highlight } from 'refractor'`). refractor v4
// exports `refractor.highlight(text, language)` at runtime — same signature —
// so `tokenize` works, but TS needs a cast. This is a known temporary debt.
// Delete once react-diff-view ships types for refractor v4+.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const refractorAdapter = refractor as unknown as any
