import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Library CSS first so our index.css overrides win the cascade. The
// react-diff-view default theme is light-mode and unreadable on the
// dark surface — index.css redefines the `--diff-*` custom properties
// to dark-mode-friendly values.
import 'react-diff-view/style/index.css'
import './index.css'
import App from './app'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
