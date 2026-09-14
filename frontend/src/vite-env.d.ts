/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the API. Empty in development, where Vite proxies /api instead. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
