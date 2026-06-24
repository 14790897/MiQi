import type { AppParams, AppResult, AppEventPayload } from './app-protocol'
import { createTypedAppClient } from './app-client'

const send = async () => ({}) as unknown
const client = createTypedAppClient(send)

const writeParams: AppParams<'fs/writeFile'> = {
  path: 'C:/repo/out.txt',
  dataBase64: '',
}

void writeParams

const readResult: AppResult<'fs/readFile'> = {
  dataBase64: 'aGVsbG8=',
}

void readResult

client.request('fs/writeFile', {
  path: 'C:/repo/out.txt',
  dataBase64: 'aGVsbG8=',
})

// @ts-expect-error fs/writeFile requires dataBase64
client.request('fs/writeFile', {
  path: 'C:/repo/out.txt',
})

client.request('fs/remove', {
  path: 'C:/repo/out.txt',
  // @ts-expect-error recursive must be boolean
  recursive: 'true',
})

// @ts-expect-error unknown App Server method
client.request('fs/nope', {
  path: 'C:/repo/out.txt',
})

const execResult: AppResult<'command/exec'> = {
  exitCode: 0,
  stdout: '',
  stderr: '',
  stdoutCapReached: false,
  stderrCapReached: false,
  durationMs: 1,
  terminationReason: 'exited',
}

void execResult

const changed: AppEventPayload<'fs/changed'> = {
  watchId: 'watch-1',
  changedPaths: ['C:/repo/a.txt'],
}

void changed

// Typed event payloads are accessible with explicit type narrowing
const outputDelta: AppEventPayload<'process/outputDelta'> = {
  processHandle: 'p',
  stream: 'stdout',
  deltaBase64: '',
  capReached: false,
}
void outputDelta

const exited: AppEventPayload<'process/exited'> = {
  processHandle: 'p',
  exitCode: 0,
  stdout: '',
  stderr: '',
  stdoutCapReached: false,
  stderrCapReached: false,
  durationMs: 1,
  terminationReason: 'exited',
}
void exited

// @ts-expect-error fs/changed event payload requires changedPaths
const badChanged: AppEventPayload<'fs/changed'> = {
  watchId: 'watch-1',
}

void badChanged
