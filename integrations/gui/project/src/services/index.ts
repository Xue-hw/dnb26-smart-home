import { configuredMode } from './connection';
import type { SmartHomeDataSource } from '@/types/contracts';
import { HttpDataSource } from './httpDataSource';
import { MockDataSource } from './mockDataSource';

export const dataMode = configuredMode();
export const dataSource: SmartHomeDataSource = dataMode === 'http' ? new HttpDataSource() : new MockDataSource();
