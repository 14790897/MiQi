import type { AppParams, AppResult } from './app-protocol'
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
