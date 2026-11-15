import type { DataMode, SmartHomeDataSource } from '@/types/contracts';
import { HttpDataSource } from './httpDataSource';
import { MockDataSource } from './mockDataSource';

export const dataMode: DataMode = import.meta.env.VITE_DATA_MODE === 'http' ? 'http' : 'mock';
export const dataSource: SmartHomeDataSource = dataMode === 'http' ? new HttpDataSource() : new MockDataSource();
