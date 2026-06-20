import { describe, expect, it } from 'vitest'
import {
  buildInitializeParams,
  normalizeBridgeMessage,
} from './bridge'

describe('normalizeBridgeMessage', () => {
  it('normalizes AppServer response request_id', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-1',
      result: { ok: true },
    })

    expect(msg.requestId).toBe('req-1')
    expect(msg.result).toEqual({ ok: true })
    expect(msg.error).toBeUndefined()
  })

  it('normalizes transport response id', () => {
    const msg = normalizeBridgeMessage({
      id: 'req-2',
      result: { ok: true },
    })

    expect(msg.requestId).toBe('req-2')
  })

  it('normalizes AppServer error code', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-3',
      error: 'Not initialized',
      code: 'NOT_INITIALIZED',
      recoverable: false,
    })

    expect(msg.requestId).toBe('req-3')
    expect(msg.error).toBe('Not initialized')
    expect(msg.code).toBe('NOT_INITIALIZED')
    expect(msg.recoverable).toBe(false)
  })

  it('normalizes legacy type events', () => {
    const msg = normalizeBridgeMessage({
      id: 'req-4',
      type: 'progress',
      data: { text: 'running' },
    })

    expect(msg.requestId).toBe('req-4')
    expect(msg.eventType).toBe('progress')
    expect(msg.data).toEqual({ text: 'running' })
  })

  it('normalizes AppServer event envelopes', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-5',
      event: 'fs/changed',
      data: { watchId: 'watch-1' },
    })

    expect(msg.requestId).toBe('req-5')
    expect(msg.eventType).toBe('fs/changed')
    expect(msg.data).toEqual({ watchId: 'watch-1' })
  })
})

describe('buildInitializeParams', () => {
  it('builds the Desktop initialize payload', () => {
    const params = buildInitializeParams('0.1.0')

    expect(params.clientId).toBe('miqi-desktop')
    expect(params.clientInfo).toEqual({
      name: 'miqi_desktop',
      title: 'MiQi Desktop',
      version: '0.1.0',
    })
    expect(params.capabilities).toEqual({
      experimentalApi: true,
      optOutNotificationMethods: [],
    })
  })
})
