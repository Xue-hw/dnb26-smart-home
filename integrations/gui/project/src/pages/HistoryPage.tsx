import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactEChartsCore from 'echarts-for-react/esm/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer]);
import { BarChart3, CalendarRange, FileImage, Filter, ImageOff, ListFilter, RefreshCw, Search, TrendingUp } from 'lucide-react';
import { DemoNotice, EmptyState, ErrorState, LoadingBlock, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { useAppData } from '@/context/AppDataContext';
import type { DeviceEvent, DeviceState, Paginated, RecognitionEvent, SensorMetric, SensorSeries } from '@/types/contracts';
import { deviceStateText, errorMessage, formatDateTime, localDateTimeValue, toIsoRange } from '@/utils';

const initialEnd = new Date();
const initialStart = new Date(initialEnd.getTime() - 24 * 60 * 60 * 1000);

export default function HistoryPage() {
  const { source, snapshot, mode } = useAppData();
  const [start, setStart] = useState(localDateTimeValue(initialStart));
  const [end, setEnd] = useState(localDateTimeValue(initialEnd));
  const [metric, setMetric] = useState<'all' | SensorMetric>('all');
  const [deviceId, setDeviceId] = useState('');
  const [series, setSeries] = useState<SensorSeries[]>([]);
  const [events, setEvents] = useState<Paginated<DeviceEvent> | null>(null);
  const [recognitions, setRecognitions] = useState<RecognitionEvent[]>([]);
  const [applied, setApplied] = useState({ start, end, metric, deviceId });
  const [page, setPage] = useState(1);
  const [recognitionTotal, setRecognitionTotal] = useState(0);
  const sequence = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const query = useCallback(async (nextPage = 1, filters = { start, end, metric, deviceId }) => {
    const { start, end, metric, deviceId } = filters;
    if (!start || !end || new Date(start).getTime() >= new Date(end).getTime()) {
      setError('开始时间必须早于结束时间。');
      return;
    }
    const requestId = ++sequence.current;
    setLoading(true);
    setError('');
    try {
      const range = toIsoRange(start, end);
      const [nextSeries, nextEvents, nextRecognitions] = await Promise.all([
        source.getSensorHistory({ ...range, metric: metric === 'all' ? undefined : metric }),
        source.getDeviceEvents({ ...range, device_id: deviceId || undefined, page: nextPage, page_size: 20 }),
        source.getRecognitionEvents({ ...range, page: nextPage, page_size: 20 }),
      ]);
      if (requestId !== sequence.current) return;
      setApplied(filters);
      setPage(nextPage);
      setRecognitionTotal(nextRecognitions.total);
      setSeries(nextSeries);
      setEvents(nextEvents);
      setRecognitions(nextRecognitions.items);
    } catch (reason) { if (requestId === sequence.current) setError(errorMessage(reason)); }
    finally { if (requestId === sequence.current) setLoading(false); }
  }, [start, end, metric, deviceId, source]);

  useEffect(() => { void query(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const temperature = useMemo(() => series.find((item) => item.metric === 'temperature')?.points || [], [series]);
  const stats = useMemo(() => {
    const values = temperature.map((point) => point.value);
    return {
      average: values.length ? (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1) : '—',
      max: values.length ? Math.max(...values).toFixed(1) : '—',
      min: values.length ? Math.min(...values).toFixed(1) : '—',
    };
  }, [temperature]);

  const chartOption = useMemo<EChartsOption>(() => ({
    backgroundColor: 'transparent',
    animationDuration: 350,
    color: ['#f19b68', '#45bde8'],
    tooltip: { trigger: 'axis', backgroundColor: '#102238', borderColor: '#2e506e', textStyle: { color: '#e6edf7', fontSize: 11 }, valueFormatter: (value) => String(value) },
    legend: { top: 0, right: 0, textStyle: { color: '#8ca1b8', fontSize: 10 }, data: series.map((item) => item.metric === 'temperature' ? '温度 °C' : '湿度 %RH') },
    grid: { left: 48, right: 48, top: 42, bottom: 42 },
    xAxis: { type: 'time', axisLine: { lineStyle: { color: '#29465f' } }, axisLabel: { color: '#6f879d', fontSize: 10, hideOverlap: true }, splitLine: { show: false } },
    yAxis: series.map((item) => ({ type: 'value', name: item.unit, nameTextStyle: { color: '#6f879d', fontSize: 10 }, axisLabel: { color: '#6f879d', fontSize: 10 }, splitLine: { lineStyle: { color: '#172d42' } }, scale: true })),
    dataZoom: [{ type: 'inside', throttle: 50 }],
    series: series.map((item, index) => ({
      name: item.metric === 'temperature' ? '温度 °C' : '湿度 %RH',
      type: 'line', smooth: true, showSymbol: false, yAxisIndex: index,
      data: item.points.map((point) => [point.ts, point.value]),
      lineStyle: { width: 2 }, areaStyle: { opacity: .07 },
    })),
  }), [series]);

  function resetFilters() {
    const now = new Date();
    setStart(localDateTimeValue(new Date(now.getTime() - 86400000)));
    setEnd(localDateTimeValue(now));
    setMetric('all');
    setDeviceId('');
  }

  function quickRange(hours: number) {
    const now = new Date();
    const filters = { start: localDateTimeValue(new Date(now.getTime() - hours * 3600000)), end: localDateTimeValue(now), metric, deviceId };
    setStart(filters.start); setEnd(filters.end); void query(1, filters);
  }

  return <>
    <PageHeader eyebrow="03 / HISTORY" title="历史数据与统计" description="按时间查看环境变化、设备活动与识别记录。编辑条件后点击查询。" actions={<button className="button secondary" onClick={() => void query()}><RefreshCw size={15} />重新查询</button>} />
    <DemoNotice>演示库预置最近 24 小时、每 30 分钟一条的温湿度记录。修改设备或运行识别后，新的事件会进入同一数据库并参与查询。</DemoNotice>
    {error && <ErrorState message={error} />}

    <div className="quick-ranges"><button className="button secondary" disabled={loading} onClick={() => quickRange(1)}>最近1小时</button><button className="button secondary" disabled={loading} onClick={() => quickRange(24)}>最近24小时</button><button className="button secondary" disabled={loading} onClick={() => quickRange(168)}>最近7天</button></div>
    <div className="filter-bar">
      <div className="form-field"><label htmlFor="history-start">开始时间</label><input id="history-start" type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="history-end">结束时间</label><input id="history-end" type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="history-metric">传感器指标</label><select id="history-metric" value={metric} onChange={(event) => setMetric(event.target.value as 'all' | SensorMetric)}><option value="all">温度 + 湿度</option><option value="temperature">仅温度</option><option value="humidity">仅湿度</option></select></div>
      <div className="form-field"><label htmlFor="history-device">事件设备</label><select id="history-device" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">全部设备</option>{snapshot?.devices.map((device: DeviceState) => <option key={device.device_id} value={device.device_id}>{device.name}</option>)}</select></div>
      <div className="page-actions"><button className="button ghost" onClick={resetFilters}><Filter size={14} />重置</button><button className="button" onClick={() => void query()}><Search size={14} />查询</button></div>
    </div>

    <div className="stats-grid"><StatCard label="平均温度" value={`${stats.average} °C`} note="当前查询区间" /><StatCard label="最高温度" value={`${stats.max} °C`} note={`${temperature.length} 个采样点`} /><StatCard label="最低温度" value={`${stats.min} °C`} note="按采样点计算" /><StatCard label="设备事件" value={events?.total ?? 0} note={`识别记录 ${recognitionTotal} 条`} /></div>

    {loading ? <LoadingBlock label="正在查询历史记录…" /> : <div className="history-stack">
      <Panel title="传感器历史曲线" description={`${formatDateTime(toIsoRange(applied.start, applied.end).start)} 至 ${formatDateTime(toIsoRange(applied.start, applied.end).end)} · 已查询区间`} icon={<TrendingUp size={17} />} actions={<StatusBadge tone="info">{mode === 'mock' ? '演示数据' : '历史数据'}</StatusBadge>}>
        {series.some((item) => item.points.length) ? <div className="chart-container"><ReactEChartsCore echarts={echarts} option={chartOption} style={{ height: '100%', width: '100%' }} notMerge /></div> : <EmptyState title="该区间没有传感器数据" description="请扩大时间范围，或确认设备已有采样记录。" />}
      </Panel>

      <Panel title="设备状态与命令事件" description={`共 ${events?.total || 0} 条，每页最多20条`} icon={<ListFilter size={17} />}>
        {events?.items.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>时间</th><th>设备</th><th>动作</th><th>最终状态</th><th>来源</th><th>命令 ID</th></tr></thead><tbody>{events.items.map((event) => <tr key={event.event_id}><td>{formatDateTime(event.occurred_at)}</td><td>{event.device_name}</td><td>{event.action}</td><td>{deviceStateText(event.state)}</td><td>{event.source}</td><td>{event.command_id || '—'}</td></tr>)}</tbody></table></div> : <EmptyState title="该区间没有设备事件" description="该页暂无事件；可调整时间区间或返回上一页。" />}
      </Panel>

      <Panel title="历史识别记录" description="查看历史图片与识别结果。图片是否归档由后端返回结果决定。" icon={<ImageOff size={17} />} actions={<StatusBadge>{recognitions.length} 条</StatusBadge>}>
        {recognitions.length ? <div className="thumbnail-grid">{recognitions.map((event) => <article className="recognition-card" key={event.event_id}><div className="recognition-thumb">{event.image_url ? <img src={event.image_url} alt={event.file_name} /> : <FileImage size={32} />}</div><div className="recognition-info"><strong>{event.type === 'object' ? '物体识别' : '人脸核验'} · {event.file_name}</strong><p>{event.result_summary}</p><small>{formatDateTime(event.occurred_at)}<br />{event.image_url ? '图片可查看' : '未返回归档图片'}</small></div></article>)}</div> : <EmptyState title="该区间没有识别记录" description="该页暂无识别记录；可调整区间或返回上一页。" />}
      </Panel>
    </div>}
    <div className="pagination"><button className="button secondary" disabled={loading || page <= 1} onClick={() => void query(page - 1, applied)}>上一页</button><span>第 {page} / {Math.max(1, Math.ceil(Math.max(events?.total || 0, recognitionTotal) / 20))} 页 · 设备与识别记录分别分页</span><button className="button secondary" disabled={loading || page * 20 >= Math.max(events?.total || 0, recognitionTotal)} onClick={() => void query(page + 1, applied)}>下一页</button></div>
    {!loading && !series.length && <div className="inline-warning"><BarChart3 size={14} /> 当前接口没有返回序列，请检查时间条件或数据适配层。</div>}
    <div className="inline-warning"><CalendarRange size={14} /> 时间按当前浏览器所在时区显示。修改筛选条件不会改变已查询的数据，点击“查询”后生效。</div>
  </>;
}

function StatCard({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <article className="stat-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}
