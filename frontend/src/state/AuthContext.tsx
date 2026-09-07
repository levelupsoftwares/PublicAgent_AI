import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { api, getToken, setToken, User } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string, phone?: string) => Promise<void>
  demoLogin: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState>({} as AuthState)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fast local bootstrap: a valid token is verified on first API call.
    if (getToken()) {
      api
        .complaints()
        .then(() => {
          // Decode name/email from the JWT payload (no /me endpoint needed for MVP).
          try {
            const payload = JSON.parse(atob(getToken()!.split('.')[1]))
            setUser({ id: payload.sub, name: payload.name || 'Citizen', email: payload.email })
          } catch {
            setToken(null)
          }
        })
        .catch(() => setToken(null))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const finish = (token: string, u: User) => {
    setToken(token)
    setUser(u)
  }

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => {
      const r = await api.login(email, password)
      finish(r.access_token, r.user)
    },
    register: async (name, email, password, phone) => {
      const r = await api.register(name, email, password, phone)
      finish(r.access_token, r.user)
    },
    demoLogin: async () => {
      const r = await api.demoLogin()
      finish(r.access_token, r.user)
    },
    logout: () => {
      setToken(null)
      setUser(null)
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
