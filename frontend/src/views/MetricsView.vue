<template>
  <div>
    <h1 class="text-h5 mb-4">Metrics Dashboard</h1>

    <v-card v-if="Object.keys(metricsStore.latestByName).length === 0">
      <v-card-text class="text-center text-medium-emphasis">
        <v-icon size="48" class="mb-2">mdi-chart-line</v-icon>
        <p>No metrics received yet.</p>
        <p class="text-caption">Metrics will appear here once the pipeline is running.</p>
      </v-card-text>
    </v-card>

    <v-row v-else>
      <v-col
        v-for="(metric, name) in metricsStore.latestByName"
        :key="String(name)"
        cols="12"
        md="4"
        lg="3"
      >
        <v-card>
          <v-card-title class="text-body-1">{{ String(name) }}</v-card-title>
          <v-card-text>
            <div class="text-h4">
              {{ typeof metric.value === 'number' ? metric.value.toFixed(1) : JSON.stringify(metric.value) }}
            </div>
            <div class="text-caption text-medium-emphasis mt-1">
              <v-chip
                v-for="(v, k) in metric.tags"
                :key="String(k)"
                size="x-small"
                class="mr-1"
                variant="outlined"
              >
                {{ k }}={{ v }}
              </v-chip>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { useMetricsStore } from '@/stores/metrics'

const metricsStore = useMetricsStore()
</script>
