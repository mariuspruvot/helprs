import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import SkillSelector, { SKILLS } from './SkillSelector'

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

afterEach(() => {
  cleanup()
})

describe('SkillSelector', () => {
  const defaultProps = {
    repoFullName: 'acme/helprs',
    prNumber: 42,
    onSelectSkill: vi.fn(),
  }

  test('renders all skill cards', () => {
    renderWithRouter(<SkillSelector {...defaultProps} />)

    for (const skill of SKILLS) {
      expect(screen.getByTestId(`skill-card-${skill.name}`)).toBeTruthy()
      expect(screen.getByText(skill.label)).toBeTruthy()
      expect(screen.getByText(skill.description)).toBeTruthy()
    }
  })

  test('renders repo and PR info in header', () => {
    renderWithRouter(<SkillSelector {...defaultProps} />)

    expect(screen.getByTestId('skill-selector')).toBeTruthy()
    const repoElements = screen.getAllByText('acme/helprs')
    expect(repoElements.length).toBeGreaterThan(0)
    const prElements = screen.getAllByText('#42')
    expect(prElements.length).toBeGreaterThan(0)
  })

  test('calls onSelectSkill when challenge-me card is clicked', () => {
    const onSelectSkill = vi.fn()
    renderWithRouter(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} />)

    fireEvent.click(screen.getByTestId('skill-card-challenge-me'))
    expect(onSelectSkill).toHaveBeenCalledWith('challenge-me')
  })

  test('does not call onSelectSkill for coming-soon skills', () => {
    const onSelectSkill = vi.fn()
    renderWithRouter(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} />)

    fireEvent.click(screen.getByTestId('skill-card-eli5'))
    fireEvent.click(screen.getByTestId('skill-card-pair-debug'))
    fireEvent.click(screen.getByTestId('skill-card-hot-seat'))
    fireEvent.click(screen.getByTestId('skill-card-test-me'))
    expect(onSelectSkill).not.toHaveBeenCalled()
  })

  test('shows "soon" badge for unreleased skills', () => {
    renderWithRouter(<SkillSelector {...defaultProps} />)

    const badges = screen.getAllByText('soon')
    expect(badges.length).toBe(4)
  })

  test('shows DEFAULT badge for challenge-me', () => {
    renderWithRouter(<SkillSelector {...defaultProps} />)
    expect(screen.getByText('DEFAULT')).toBeTruthy()
  })

  test('disables cards when disabled prop is true', () => {
    renderWithRouter(<SkillSelector {...defaultProps} disabled={true} />)

    for (const skill of SKILLS) {
      const card = screen.getByTestId(`skill-card-${skill.name}`) as HTMLButtonElement
      expect(card.disabled).toBe(true)
    }
  })

  test('does not call onSelectSkill when disabled', () => {
    const onSelectSkill = vi.fn()
    renderWithRouter(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} disabled={true} />)

    fireEvent.click(screen.getByTestId('skill-card-challenge-me'))
    expect(onSelectSkill).not.toHaveBeenCalled()
  })

  test('renders helPRs branding', () => {
    renderWithRouter(<SkillSelector {...defaultProps} />)
    const brandElements = screen.getAllByText('helPRs')
    expect(brandElements.length).toBeGreaterThan(0)
  })

  test('renders 5 skills total (1 active + 4 coming soon)', () => {
    expect(SKILLS.length).toBe(5)
    expect(SKILLS.filter(s => !s.comingSoon).length).toBe(1)
    expect(SKILLS.filter(s => s.comingSoon).length).toBe(4)
  })
})
