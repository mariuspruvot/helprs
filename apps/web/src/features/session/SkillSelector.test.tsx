import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import SkillSelector, { SKILLS } from './SkillSelector'

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
    render(<SkillSelector {...defaultProps} />)

    for (const skill of SKILLS) {
      expect(screen.getByTestId(`skill-card-${skill.name}`)).toBeTruthy()
      expect(screen.getByText(skill.label)).toBeTruthy()
      expect(screen.getByText(skill.description)).toBeTruthy()
      expect(screen.getByText(skill.duration)).toBeTruthy()
    }
  })

  test('renders repo and PR info in header', () => {
    render(<SkillSelector {...defaultProps} />)

    expect(screen.getByTestId('skill-selector')).toBeTruthy()
    // Use getAllByText since repo name may appear in multiple places
    const repoElements = screen.getAllByText('acme/helprs')
    expect(repoElements.length).toBeGreaterThan(0)
    const prElements = screen.getAllByText('#42')
    expect(prElements.length).toBeGreaterThan(0)
  })

  test('calls onSelectSkill when an available skill card is clicked', () => {
    const onSelectSkill = vi.fn()
    render(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} />)

    fireEvent.click(screen.getByTestId('skill-card-challenge-me'))
    expect(onSelectSkill).toHaveBeenCalledWith('challenge-me')
  })

  test('does not call onSelectSkill for coming-soon skills', () => {
    const onSelectSkill = vi.fn()
    render(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} />)

    fireEvent.click(screen.getByTestId('skill-card-code-review'))
    fireEvent.click(screen.getByTestId('skill-card-security-audit'))
    expect(onSelectSkill).not.toHaveBeenCalled()
  })

  test('shows Coming soon badge for unreleased skills', () => {
    render(<SkillSelector {...defaultProps} />)

    const badges = screen.getAllByText('Coming soon')
    expect(badges.length).toBe(2)
  })

  test('disables cards when disabled prop is true', () => {
    render(<SkillSelector {...defaultProps} disabled={true} />)

    for (const skill of SKILLS) {
      const card = screen.getByTestId(`skill-card-${skill.name}`) as HTMLButtonElement
      expect(card.disabled).toBe(true)
    }
  })

  test('does not call onSelectSkill when disabled', () => {
    const onSelectSkill = vi.fn()
    render(<SkillSelector {...defaultProps} onSelectSkill={onSelectSkill} disabled={true} />)

    fireEvent.click(screen.getByTestId('skill-card-challenge-me'))
    expect(onSelectSkill).not.toHaveBeenCalled()
  })

  test('renders helPRs branding', () => {
    render(<SkillSelector {...defaultProps} />)
    const brandElements = screen.getAllByText('helPRs')
    expect(brandElements.length).toBeGreaterThan(0)
  })

  test('renders disclaimer text', () => {
    render(<SkillSelector {...defaultProps} />)
    expect(
      screen.getByText(/AI-generated content may be inaccurate/),
    ).toBeTruthy()
  })
})
