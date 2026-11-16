import type { CapacitorConfig } from '@capacitor/cli';
const config: CapacitorConfig = {
  appId: 'com.dnb26.smarthome',
  appName: 'DnB26 智慧家',
  webDir: 'dist',
  // HTTP is restricted to explicit LAN hosts by Android network_security_config.xml.
  android: { backgroundColor: '#f4f3ee', allowMixedContent: true },
};
export default config;
