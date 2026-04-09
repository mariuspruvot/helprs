import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import App from './app'

test('renders helPRs heading', () => {
  render(<App />)
  expect(screen.getByText('helPRs')).toBeDefined()
})
