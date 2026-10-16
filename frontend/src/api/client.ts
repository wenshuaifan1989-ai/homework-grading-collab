import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (error) => {
    const url = String(error.config?.url || '')
    const isPublicAuthRequest = url.endsWith('/users/login') || url.endsWith('/users/register')
    if (error.response?.status === 401 && !isPublicAuthRequest) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      sessionStorage.removeItem('active_role')
      if (window.location.pathname !== '/') window.location.assign('/')
    }
    return Promise.reject(error)
  },
)

export default client
