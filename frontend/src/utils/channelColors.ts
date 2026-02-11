export const CHANNEL_PALETTE = [
  '#42A5F5', '#66BB6A', '#FFA726', '#EF5350',
  '#AB47BC', '#26C6DA', '#EC407A', '#8D6E63',
] as const

export function channelColor(channel: string): string {
  let hash = 0
  for (let i = 0; i < channel.length; i++) hash = (hash * 31 + channel.charCodeAt(i)) | 0
  return CHANNEL_PALETTE[Math.abs(hash) % CHANNEL_PALETTE.length]
}
