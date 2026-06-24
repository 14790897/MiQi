import type {
  AppMethod,
  AppMethodParams,
  AppMethodResult,
  AppMethodEvents,
} from './app-protocol'

export type AppEventHandler<M extends AppMethod = AppMethod> = (
  type: AppMethodEvents[M],
  data: unknown,
) => void

export type UntypedAppSend = (
  method: string,
  params?: Record<string, unknown>,
  onEvent?: (type: string, data: unknown) => void,
) => Promise<unknown>

export interface TypedAppClient {
  request<M extends AppMethod>(
    method: M,
    params: AppMethodParams[M],
    onEvent?: AppEventHandler<M>,
  ): Promise<AppMethodResult[M]>
}

export function createTypedAppClient(send: UntypedAppSend): TypedAppClient {
  return {
    async request(method, params, onEvent) {
      return await send(
        method,
        params as Record<string, unknown>,
        onEvent as ((type: string, data: unknown) => void) | undefined,
      ) as AppMethodResult[typeof method]
    },
  }
}
