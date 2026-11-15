import { useCallback, useEffect, useMemo, useState } from 'react';
import { LoaderCircle, Plus, Search, ShieldCheck, Trash2, UserRound, UsersRound } from 'lucide-react';
import { DemoNotice, EmptyState, ErrorState, LoadingBlock, Modal, PageHeader, StatusBadge } from '@/components/Common';
import { useAppData } from '@/context/AppDataContext';
import type { Person } from '@/types/contracts';
import { errorMessage, formatDateTime } from '@/utils';

export default function PersonnelPage() {
  const { source, mode } = useAppData();
  const [persons, setPersons] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState('');
  const [userId, setUserId] = useState('');
  const [faceImage, setFaceImage] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  useEffect(() => {
    if (!faceImage) { setPreview(''); return; }
    const url = URL.createObjectURL(faceImage); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [faceImage]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Person | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadPersons = useCallback(async () => {
    setError('');
    try { setPersons(await source.getPersons()); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [source]);

  useEffect(() => { void loadPersons(); }, [loadPersons]);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return persons.filter((person) => !keyword || person.name.toLowerCase().includes(keyword) || person.user_id.toLowerCase().includes(keyword));
  }, [persons, search]);

  function openAdd() {
    setName(''); setUserId(''); setFaceImage(null); setFormError(''); setShowAdd(true);
  }

  async function submitPerson(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !userId.trim()) { setFormError('请填写姓名和人员 ID。'); return; }
    if (faceImage && (!['image/jpeg', 'image/png', 'image/webp'].includes(faceImage.type) || faceImage.size > 8 * 1024 * 1024)) { setFormError('请选择不超过8 MB的 JPG、PNG 或 WebP 图片。'); return; }
    setSubmitting(true); setFormError('');
    try {
      await source.addPerson({ name, user_id: userId, face_image: faceImage });
      setShowAdd(false);
      await loadPersons();
    } catch (reason) { setFormError(errorMessage(reason)); }
    finally { setSubmitting(false); }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setError('');
    try {
      await source.deletePerson(deleteTarget.user_id);
      setDeleteTarget(null);
      await loadPersons();
    } catch (reason) {
      setError(`删除失败：${errorMessage(reason)} 人员仍保留在数据库中，未做本地隐藏。`);
    } finally { setDeleting(false); }
  }

  return <>
    <PageHeader eyebrow="04 / AUTHORIZATION" title="授权人员管理" description="管理可通行人员，并查看人脸录入状态。" actions={<button className="button" onClick={openAdd}><Plus size={16} />新增授权人员</button>} />
    <DemoNotice>本地数据库预置两名演示人员。演示资料会保存在当前浏览器中；照片仅预览，不录入人脸。</DemoNotice>
    {error && <ErrorState message={error} retry={() => void loadPersons()} />}
    <div className="filter-bar" style={{ gridTemplateColumns: '1fr auto' }}><div className="form-field"><label htmlFor="person-search">搜索姓名或人员 ID</label><input id="person-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="例如 DNB001" /></div><StatusBadge tone="info">共 {persons.length} 人</StatusBadge></div>
    {loading ? <LoadingBlock label="正在读取授权人员…" /> : filtered.length ? <div className="personnel-grid">{filtered.map((person) => <article className="person-card" key={person.user_id}><div className="person-top"><div className="avatar"><span>{person.name.slice(0, 1)}</span>{person.avatar_url ? <img src={person.avatar_url} alt={person.name} onError={e => { e.currentTarget.style.display = 'none'; }} /> : null}</div><div><h3>{person.name}</h3><p>{person.user_id}</p></div></div><div className="person-meta"><div><span>人员记录</span><StatusBadge tone="info">{mode === 'mock' ? '演示人员' : '已添加'}</StatusBadge></div><div><span>录入时间</span><span>{formatDateTime(person.created_at)}</span></div><div><span>人脸录入</span><span>{mode === 'mock' ? '未录入（模拟资料）' : '待后端确认'}</span></div></div><div className="person-actions"><span className="form-help"><ShieldCheck size={13} /> 人员资料已保存</span><button className="button danger small" onClick={() => setDeleteTarget(person)}><Trash2 size={13} />删除</button></div></article>)}</div> : <EmptyState title={search ? '没有匹配人员' : '暂无授权人员'} description={search ? '请更换搜索关键词。' : '点击右上角新增第一名人员。'} action={search ? <button className="button secondary small" onClick={() => setSearch('')}><Search size={14} />清除搜索</button> : undefined} />}

    {showAdd && <Modal title="新增授权人员" description={mode === 'mock' ? '演示模式仅保存姓名和编号，不录入真实人脸。' : '将调用真实人员新增接口。'} onClose={() => { if (!submitting) setShowAdd(false); }}><form onSubmit={(event) => void submitPerson(event)}><div style={{ display: 'grid', gap: 15 }}><div className="form-field"><label htmlFor="person-name">姓名</label><input id="person-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如 王同学" maxLength={30} autoFocus /></div><div className="form-field"><label htmlFor="person-id">人员 ID</label><input id="person-id" value={userId} onChange={(event) => setUserId(event.target.value)} placeholder="例如 DNB003" maxLength={32} /><span className="form-help">每个人使用唯一编号，不能重复。</span></div><div className="form-field"><label htmlFor="person-image">人脸照片</label><input id="person-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setFaceImage(event.target.files?.[0] || null)} /><span className="form-help">JPG、PNG、WebP，最大8 MB。{mode === 'mock' ? '演示模式仅预览，不录入人脸。' : '照片将提交后端，录入结果需由后端确认。'}</span>{preview && <img className="face-upload-preview" src={preview} alt="待提交人脸照片" />}</div></div>{formError && <p className="form-error" style={{ marginTop: 14 }}>{formError}</p>}<div className="form-actions"><button type="button" className="button ghost" disabled={submitting} onClick={() => setShowAdd(false)}>取消</button><button type="submit" className="button" disabled={submitting}>{submitting ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />}{submitting ? '正在提交…' : '确认新增'}</button></div></form></Modal>}

    {deleteTarget && <Modal title="删除授权人员" description="此操作会修改当前数据源。只有接口成功后，列表才会移除该人员。" onClose={() => { if (!deleting) setDeleteTarget(null); }}><div className="demo-notice"><UserRound size={18} /><div>确认删除 <strong>{deleteTarget.name}</strong>（{deleteTarget.user_id}）？<br />{mode === 'mock' ? '仅删除当前浏览器的演示资料。' : '将提交人员删除请求，请确认姓名和编号。'}</div></div><div className="form-actions"><button className="button ghost" disabled={deleting} onClick={() => setDeleteTarget(null)}>取消</button><button className="button danger" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}{deleting ? '正在删除…' : '确认删除'}</button></div></Modal>}
    <div className="inline-warning"><UsersRound size={14} /> 人员添加成功与人脸录入成功是两个状态；真实录入结果将在后端接入后展示。</div>
  </>;
}
