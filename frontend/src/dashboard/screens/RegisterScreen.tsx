import { useEffect, useMemo, useRef, useState } from 'react';
import { Panel } from '../components';
import { useRegistered } from '../../hooks/useCatalog';
import {
  CATEGORY_TREE,
  DRAFT_PRODUCT_ID,
  EMPTY_FORM,
  KRW_PER_USD,
  fromProduct,
  removeRegistered,
  saveRegistered,
  setDraft,
  validateForm,
} from '../../lib/productRegistry';
import type { RegistrationForm } from '../../lib/productRegistry';
import { HIGHLIGHT_GROUPS, SECONDARY_CATEGORIES, labelKo } from '../../lib/formLabels';

const DRAFT_DEBOUNCE_MS = 250;
/** 대표 이미지 파일 상한. localStorage 에 data URL 로 들어가므로 작게 */
const MAX_IMAGE_BYTES = 400 * 1024;

/**
 * 상품 등록 — 왼쪽은 계약 `product-registration-spec.md` 의 입력 필드, 오른쪽은
 * **실제 쇼핑몰 상세 페이지** 를 iframe 으로 띄운 미리보기다.
 *
 * 폼이 바뀌면 초안을 localStorage 에 쓰고, 쇼핑몰(`/?product=DRAFT&preview=1`)이 storage
 * 이벤트로 그대로 다시 그린다. 미리보기용 컴포넌트를 따로 만들지 않는 이유는 그러면 언젠가
 * 둘이 달라지기 때문이다. 사장님이 본 것과 고객이 볼 것이 같은 코드여야 한다.
 */
export default function RegisterScreen() {
  const mine = useRegistered();

  const [form, setForm] = useState<RegistrationForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  const { errors, warnings } = useMemo(() => validateForm(form), [form]);
  const tertiaries = CATEGORY_TREE.get(form.secondary_category) ?? [];

  // 폼 → 초안. 디바운스해서 쇼핑몰 미리보기가 타자마다 다시 그리지 않게 한다
  useEffect(() => {
    const id = window.setTimeout(() => setDraft(form), DRAFT_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [form]);

  // 화면을 떠나면 초안을 지운다. 초안이 남아 있으면 쇼핑몰 목록 맨 앞에 계속 뜬다
  useEffect(() => () => setDraft(null), []);

  const set = <K extends keyof RegistrationForm>(key: K, value: RegistrationForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const toggleHighlight = (value: string) =>
    setForm((prev) => ({
      ...prev,
      highlights: prev.highlights.includes(value)
        ? prev.highlights.filter((h) => h !== value)
        : [...prev.highlights, value],
    }));

  const onImageFile = (file: File | null) => {
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      setSavedMsg(`이미지가 ${Math.round(MAX_IMAGE_BYTES / 1024)}KB 를 넘습니다. 더 작은 파일을 골라 주세요.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => set('image_url', String(reader.result ?? ''));
    reader.readAsDataURL(file);
  };

  const save = () => {
    if (errors.length) return;
    const item = saveRegistered(form, editingId ?? undefined);
    setSavedMsg(`${item.product.product_name} 을(를) ${editingId ? '수정' : '등록'}했습니다. 쇼핑몰에 바로 보입니다.`);
    setForm(EMPTY_FORM);
    setEditingId(null);
  };

  const edit = (id: string) => {
    const r = mine.find((m) => m.product.product_id === id);
    if (!r) return;
    setForm(fromProduct(r.product));
    setEditingId(id);
    setSavedMsg(null);
    setPreviewKey((k) => k + 1);
  };

  const previewSrc = `/?product=${DRAFT_PRODUCT_ID}&preview=1`;

  return (
    <div className="stack">
      <div className="register">
        <div className="register__form">
          <Panel title={editingId ? '상품 수정' : '상품 등록'} aside={editingId ? editingId : '새 상품'}>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-name">상품명 *</label>
              <input id="reg-name" className="reg-input" value={form.product_name} onChange={(e) => set('product_name', e.target.value)} placeholder="예: 진정 수분 세럼" maxLength={80} />
            </div>

            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-brand">브랜드</label>
                <input id="reg-brand" className="reg-input" value={form.brand_name} readOnly />
              </div>
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-price">가격 (원) *</label>
                <input id="reg-price" className="reg-input" type="number" min={0} step={100} value={form.price_krw} onChange={(e) => set('price_krw', e.target.value === '' ? '' : Number(e.target.value))} placeholder="32000" />
                <p className="reg-hint">고객 화면에는 ${form.price_krw === '' ? '—' : (Number(form.price_krw) / KRW_PER_USD).toFixed(2)} 로 보입니다 (고정 환율 {KRW_PER_USD}원, 계약 §4.1)</p>
              </div>
            </div>

            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-sec">대분류 *</label>
                <select id="reg-sec" className="reg-input" value={form.secondary_category} onChange={(e) => { set('secondary_category', e.target.value); set('tertiary_category', ''); }}>
                  <option value="">선택</option>
                  {SECONDARY_CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.ko} ({c.value})</option>
                  ))}
                </select>
              </div>
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-ter">세부 분류 *</label>
                <select id="reg-ter" className="reg-input" value={form.tertiary_category} disabled={!form.secondary_category} onChange={(e) => set('tertiary_category', e.target.value)}>
                  <option value="">선택</option>
                  {tertiaries.map((t) => (
                    <option key={t} value={t}>{labelKo(t)} ({t})</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-size">용량</label>
              <input id="reg-size" className="reg-input" value={form.size} onChange={(e) => set('size', e.target.value)} placeholder="50ml" maxLength={30} />
            </div>

            {HIGHLIGHT_GROUPS.map((g) => (
              <div className="reg-field" key={g.group}>
                <span className="reg-label">
                  {g.ko} <span className="reg-hint-inline">{g.hint}</span>
                </span>
                <div className="chips">
                  {g.options.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      className={`chip${form.highlights.includes(o.value) ? ' chip--hit' : ''}`}
                      aria-pressed={form.highlights.includes(o.value)}
                      onClick={() => toggleHighlight(o.value)}
                    >
                      {o.ko}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-ing">전성분 *</label>
              <textarea id="reg-ing" className="reg-input reg-textarea" rows={4} value={form.ingredients} onChange={(e) => set('ingredients', e.target.value)} placeholder="정제수, 글리세린, 나이아신아마이드, 병풀추출물 … (한글·영문 모두 됩니다. 함량 순서대로)" />
              <p className="reg-hint">성분은 태그로 받지 않습니다. 추천은 전성분의 순서에서 성분을 읽습니다 (계약 §3.1).</p>
            </div>

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-what">이 제품은 (한 문단)</label>
              <textarea id="reg-what" className="reg-input reg-textarea" rows={3} value={form.what_it_is} onChange={(e) => set('what_it_is', e.target.value)} placeholder="어떤 피부의 어떤 고민을 위해 만든 제품인지" />
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-hi">앞세울 성분 (줄마다 "성분: 설명")</label>
              <textarea id="reg-hi" className="reg-input reg-textarea" rows={3} value={form.highlighted_ingredients} onChange={(e) => set('highlighted_ingredients', e.target.value)} placeholder={'병풀추출물: 각질 제거 후 진정\n나이아신아마이드: 톤과 결 정돈'} />
            </div>
            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-callout">성분 안내 (무첨가·주의)</label>
                <input id="reg-callout" className="reg-input" value={form.ingredient_callouts} onChange={(e) => set('ingredient_callouts', e.target.value)} placeholder="파라벤 무첨가. 향료 포함" />
              </div>
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-usage">사용법</label>
              <textarea id="reg-usage" className="reg-input reg-textarea" rows={3} value={form.suggested_usage} onChange={(e) => set('suggested_usage', e.target.value)} placeholder="토너 후 2~3방울을 …" />
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-story">브랜드 이야기</label>
              <textarea id="reg-story" className="reg-input reg-textarea" rows={3} value={form.brand_story} onChange={(e) => set('brand_story', e.target.value)} placeholder="왜 이 브랜드를 만들었는지. 고객이 의견을 남길 때 보는 자리입니다" />
            </div>

            <div className="reg-field">
              <span className="reg-label">대표 이미지</span>
              <div className="reg-row">
                <input className="reg-input" value={form.image_url.startsWith('data:') ? '(업로드한 파일)' : form.image_url} onChange={(e) => set('image_url', e.target.value)} placeholder="이미지 URL 또는 파일 업로드" />
                <input type="file" accept="image/*" onChange={(e) => onImageFile(e.target.files?.[0] ?? null)} />
              </div>
            </div>

            {errors.length ? (
              <ul className="reg-msgs reg-msgs--error">
                {errors.map((m) => <li key={m}>{m}</li>)}
              </ul>
            ) : null}
            {warnings.length ? (
              <ul className="reg-msgs reg-msgs--warn">
                {warnings.map((m) => <li key={m}>{m}</li>)}
              </ul>
            ) : null}

            <div className="reg-actions">
              <button type="button" className="chip chip--hit reg-save" disabled={errors.length > 0} onClick={save}>
                {editingId ? '수정 저장' : '쇼핑몰에 등록'}
              </button>
              {editingId ? (
                <button type="button" className="chip" onClick={() => { setForm(EMPTY_FORM); setEditingId(null); }}>
                  취소
                </button>
              ) : null}
              {savedMsg ? <span className="reg-saved">{savedMsg}</span> : null}
            </div>
          </Panel>

          <Panel title="등록한 상품" aside={`${mine.length}개`}>
            {mine.length === 0 ? (
              <p className="reg-empty">아직 없습니다. 등록하면 쇼핑몰 목록·상세와 추천 후보에 바로 들어갑니다.</p>
            ) : (
              <ul className="reg-list">
                {mine.map((r) => (
                  <li key={r.product.product_id} className="reg-list__item">
                    <span className="reg-list__name">{r.product.product_name}</span>
                    <span className="reg-list__meta">
                      {labelKo(r.product.category[2] ?? r.product.category[1] ?? '')} · ${r.product.price_usd} · {r.updated_at.slice(0, 10)}
                    </span>
                    <span className="reg-list__actions">
                      <a className="chip" href={`/?product=${r.product.product_id}`} target="_blank" rel="noopener">쇼핑몰에서 보기</a>
                      <button type="button" className="chip" onClick={() => edit(r.product.product_id)}>수정</button>
                      <button type="button" className="chip" onClick={() => removeRegistered(r.product.product_id)}>삭제</button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="register__preview">
          <div className="register__preview-head">
            <strong>고객이 보게 될 상세 페이지</strong>
            <span>실제 쇼핑몰 화면입니다. 입력하면 바로 바뀝니다.</span>
            <button type="button" className="chip" onClick={() => setPreviewKey((k) => k + 1)}>새로고침</button>
          </div>
          <iframe
            key={previewKey}
            ref={iframeRef}
            className="register__iframe"
            title="상세 페이지 미리보기"
            src={previewSrc}
          />
        </div>
      </div>
    </div>
  );
}
