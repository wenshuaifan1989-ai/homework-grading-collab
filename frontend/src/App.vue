<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import AppLayout from '@/components/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()
const isAuthPage = computed(() => ['rolePortal', 'register'].includes(route.name as string))
</script>

<template>
  <AppLayout v-if="!isAuthPage">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" :key="`${auth.activeRole}:${route.fullPath}`" />
      </transition>
    </router-view>
  </AppLayout>
  <router-view v-else v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>
