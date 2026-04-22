import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-bg text-ink flex items-center justify-center p-6">
          <div className="max-w-md text-center">
            <h1 className="font-mono text-lg font-bold text-danger mb-2">Something went wrong</h1>
            <p className="text-dim text-sm font-mono mb-4">
              // {this.state.error?.message ?? 'Unknown error'}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.href = '/installations'
              }}
              className="font-mono text-sm text-accent hover:underline cursor-pointer"
            >
              {'\u2190'} Back to dashboard
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
