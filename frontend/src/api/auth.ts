import client from './client'

export interface User {
  id: number
  username: string
  email?: string | null
  phone?: string | null
  full_name?: string
  role: string
  roles: string[]
  is_active: boolean
  created_at: string
}

export type LoginRequest =
  | { phone: string; password: string }
  | { identifier: string; password: string }
  | { email: string; password: string }

export interface RegisterRequest {
  phone: string
  password: string
  full_name?: string
  email?: string
  role?: 'student'
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export const authApi = {
  login(data: LoginRequest) {
    return client.post<TokenResponse>('/users/login', data)
  },
  register(data: RegisterRequest) {
    return client.post<User>('/users/register', data)
  },
  getMe() {
    return client.get<User>('/users/me')
  },
  getUser(userId: number) {
    return client.get<User>(`/users/${userId}`)
  },
  updateUserStatus(userId: number, isActive: boolean) {
    return client.put<User>(`/users/${userId}/status`, null, {
      params: { is_active: isActive },
    })
  },
}
