import { create } from 'zustand'

interface User {
  id: string
  github_id: number
  github_login: string
  email: string | null
  avatar_url: string | null
  created_at: string
}

interface AuthState {
  accessToken: string | null
  user: User | null
  isAuthenticated: boolean
  returnUrl: string | null
  login: (token: string) => void
  logout: () => void
  setUser: (user: User) => void
  setReturnUrl: (url: string | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  returnUrl: null,

  login: (token: string) => {
    set({ accessToken: token, isAuthenticated: true })
  },

  logout: () => {
    set({ accessToken: null, user: null, isAuthenticated: false })
  },

  setUser: (user: User) => {
    set({ user })
  },

  setReturnUrl: (url: string | null) => {
    set({ returnUrl: url })
  },
}))
