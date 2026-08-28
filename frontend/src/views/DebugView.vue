<template>
  <div>
    <h1 class="text-h5 mb-4">Debug Controls</h1>

    <!-- Debug state -->
    <v-card class="mb-4">
      <v-card-title>
        <v-icon class="mr-2">mdi-bug</v-icon>
        Debug State
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="auto">
            <v-chip :color="stateColor" size="large">
              {{ debugStore.state }}
            </v-chip>
          </v-col>
          <v-col cols="auto">
            <v-btn-group>
              <v-btn
                color="warning"
                :disabled="debugStore.state === 'paused' || debugStore.state === 'inactive'"
                @click="debug.pause()"
              >
                <v-icon>mdi-pause</v-icon>
                Pause
              </v-btn>
              <v-btn
                color="success"
                :disabled="debugStore.state !== 'paused'"
                @click="debug.resume()"
              >
                <v-icon>mdi-play</v-icon>
                Resume
              </v-btn>
              <v-btn
                color="info"
                :disabled="debugStore.state !== 'paused' || debugStore.stepPending"
                :loading="debugStore.stepPending"
                @click="debug.step()"
              >
                <v-icon>mdi-skip-next</v-icon>
                Step
              </v-btn>
            </v-btn-group>
          </v-col>
          <v-col cols="auto">
            <v-chip size="small" variant="outlined">
              Steps: {{ debugStore.stepCount }}
            </v-chip>
          </v-col>
          <v-col v-if="debugStore.stepPending" cols="auto">
            <!-- A step advances when the next message arrives; on a quiet
                 pipeline that can be a while, and silence would otherwise be
                 indistinguishable from a lost command. -->
            <v-chip size="small" color="info" variant="tonal">
              <v-icon start size="small">mdi-timer-sand</v-icon>
              Waiting for the next message
            </v-chip>
          </v-col>
        </v-row>

        <v-row class="mt-2">
          <v-col cols="auto">
            <v-select
              :model-value="debugStore.granularity"
              :items="['message', 'stage', 'breakpoint']"
              label="Granularity"
              density="compact"
              hide-details
              style="width: 200px"
              @update:model-value="(v: any) => debug.setGranularity(v)"
            />
          </v-col>
          <v-col cols="auto">
            <v-switch
              :model-value="debugStore.slowMotion"
              label="Slow motion"
              density="compact"
              hide-details
              @update:model-value="(v: any) => debug.setSlowMotion(!!v)"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Breakpoints -->
    <v-card>
      <v-card-title>
        <v-icon class="mr-2">mdi-circle-outline</v-icon>
        Breakpoints
      </v-card-title>
      <v-card-text>
        <v-table v-if="debugStore.breakpoints.length > 0" density="compact">
          <thead>
            <tr>
              <th>ID</th>
              <th>Channel</th>
              <th>Condition</th>
              <th>Hits</th>
              <th>Enabled</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bp in debugStore.breakpoints" :key="bp.id">
              <td class="text-caption">{{ bp.id }}</td>
              <td>{{ bp.channel_pattern }}</td>
              <td>{{ bp.condition ?? '-' }}</td>
              <td>{{ bp.hit_count }}</td>
              <td>
                <v-icon :color="bp.enabled ? 'green' : 'grey'">
                  {{ bp.enabled ? 'mdi-check-circle' : 'mdi-circle-outline' }}
                </v-icon>
              </td>
            </tr>
          </tbody>
        </v-table>
        <p v-else class="text-medium-emphasis">
          No breakpoints set. Use the API to add breakpoints.
        </p>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDebugStore } from '@/stores/debug'
import { useDebug } from '@/composables/useDebug'

const debugStore = useDebugStore()
const debug = useDebug()

const stateColor = computed(() => {
  switch (debugStore.state) {
    case 'running': return 'green'
    case 'paused': return 'orange'
    case 'stepping': return 'blue'
    default: return 'grey'
  }
})
</script>
