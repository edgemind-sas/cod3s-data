<template>
  <div>
    <h1 class="text-h5 mb-4">Message Inspector</h1>

    <v-card v-if="messagesStore.messageCount === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-email-search-outline</v-icon>
        <p>No messages captured yet.</p>
        <p class="text-caption">Messages will appear here as they flow through the pipeline.</p>
      </v-card-text>
    </v-card>

    <template v-else>
      <v-chip class="mb-4 mr-2" size="small" color="primary">
        {{ messagesStore.messageCount }} messages
      </v-chip>
      <v-chip
        v-for="ch in messagesStore.channels"
        :key="ch"
        class="mb-4 mr-2"
        size="small"
        variant="outlined"
      >
        {{ ch }}
      </v-chip>

      <v-table density="compact">
        <thead>
          <tr>
            <th>Time</th>
            <th>Channel</th>
            <th>Key</th>
            <th>Subscribers</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(msg, i) in recentMessages" :key="i">
            <td class="text-caption">{{ formatTime(msg.timestamp) }}</td>
            <td>
              <v-chip size="x-small" variant="tonal">{{ msg.channel }}</v-chip>
            </td>
            <td>{{ msg.key ?? '-' }}</td>
            <td>{{ msg.subscriber_count }}</td>
          </tr>
        </tbody>
      </v-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMessagesStore } from '@/stores/messages'

const messagesStore = useMessagesStore()

const recentMessages = computed(() =>
  [...messagesStore.messages].reverse().slice(0, 100)
)

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString()
  } catch {
    return ts
  }
}
</script>
