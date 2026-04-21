/**
 * Shiki highlighter singleton — sync initialization with JS regex engine.
 *
 * Bundles only the languages commonly seen in Claude Code output.
 * Uses github-dark theme to match the app's dark aesthetic.
 */

import { createHighlighterCoreSync } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'
import githubDark from '@shikijs/themes/github-dark'
import langBash from '@shikijs/langs/bash'
import langCss from '@shikijs/langs/css'
import langDiff from '@shikijs/langs/diff'
import langHtml from '@shikijs/langs/html'
import langJavascript from '@shikijs/langs/javascript'
import langJsx from '@shikijs/langs/jsx'
import langJson from '@shikijs/langs/json'
import langMarkdown from '@shikijs/langs/markdown'
import langPython from '@shikijs/langs/python'
import langTypescript from '@shikijs/langs/typescript'
import langTsx from '@shikijs/langs/tsx'
import langYaml from '@shikijs/langs/yaml'

export const highlighter = createHighlighterCoreSync({
  themes: [githubDark],
  langs: [
    langBash,
    langCss,
    langDiff,
    langHtml,
    langJavascript,
    langJsx,
    langJson,
    langMarkdown,
    langPython,
    langTypescript,
    langTsx,
    langYaml,
  ],
  engine: createJavaScriptRegexEngine(),
})

export const SHIKI_THEME = 'github-dark'

/** Languages the highlighter knows about. Used to decide highlight vs plaintext. */
export const SUPPORTED_LANGS = new Set([
  'bash', 'sh', 'shell', 'zsh',
  'css',
  'diff',
  'html', 'htm',
  'javascript', 'js', 'jsx',
  'json', 'jsonc',
  'markdown', 'md',
  'python', 'py',
  'typescript', 'ts', 'tsx',
  'yaml', 'yml',
])
