<template>
  <div>
    <h1 class="text-h5 mb-4">Temporal Timeline</h1>

    <v-card>
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-timeline</v-icon>
        <p>Timeline visualization</p>
        <p class="text-caption">
          {{ messagesStore.messageCount }} messages captured.
          Swim lane timeline coming in Phase 8.
        </p>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { useMessagesStore } from '@/stores/messages'

const messagesStore = useMessagesStore()
</script>
