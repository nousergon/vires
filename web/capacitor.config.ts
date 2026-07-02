import type { CapacitorConfig } from '@capacitor/cli'

// Native shell that wraps the existing Vite PWA (vires-ops#37). The PWA still
// builds and runs standalone (`npm run build` → `dist/`); Capacitor wraps that
// build, it does not replace it. `webDir` points at the standard Vite output.
//
// Generating the native projects (`npx cap add ios` / `npx cap add android`)
// and the HealthKit / Health Connect plugin native code requires Xcode / the
// Android SDK + a device and is done outside this repo's CI.
const config: CapacitorConfig = {
  appId: 'com.nousergon.vires',
  appName: 'Vires',
  webDir: 'dist',
}

export default config
