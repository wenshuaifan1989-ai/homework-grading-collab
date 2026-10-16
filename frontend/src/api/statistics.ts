import client from './client'
import type { ApiResponse } from './homework'

export interface UserStats {
  task_count: number
  completed_count: number
  avg_score: number
  latest_score: number
}

export interface GlobalStats {
  user_count: number
  task_count: number
  completed_count: number
  avg_score: number
}

export const statsApi = {
  getUserStats(userId: number) {
    return client.get<ApiResponse<UserStats>>(`/statistics/user/${userId}`)
  },
  getGlobalStats() {
    return client.get<ApiResponse<GlobalStats>>('/statistics/global')
  },
}
