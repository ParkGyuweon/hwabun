import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { Panel } from '../components';
import { useRegistered } from '../../hooks/useCatalog';
import {
  CATEGORY_TREE,
  DRAFT_PRODUCT_ID,
  EMPTY_FORM,
  KRW_PER_USD,
  recommendPriceBin,
  fromProduct,
  removeRegistered,
  registerProduct,
  setDraft,
  validateForm,
} from '../../lib/productRegistry';
import type { RegistrationForm } from '../../lib/productRegistry';
import { HIGHLIGHT_GROUPS, SECONDARY_CATEGORIES, labelKo } from '../../lib/formLabels';

const DRAFT_DEBOUNCE_MS = 250;
/** 대표 이미지 파일 상한. localStorage 에 data URL 로 들어가므로 작게 */
const MAX_IMAGE_BYTES = 400 * 1024;

/** 필수 항목. 화면 맨 위 진행 표시와 칸별 안내가 이 목록을 본다 */
type RequiredField = 'product_name' | 'price_krw' | 'secondary_category' | 'tertiary_category' | 'ingredients';
const REQUIRED: Array<{ key: RequiredField; ko: string; section: 1 | 3 }> = [
  { key: 'product_name', ko: '상품명', section: 1 },
  { key: 'price_krw', ko: '가격', section: 1 },
  { key: 'secondary_category', ko: '대분류', section: 1 },
  { key: 'tertiary_category', ko: '세부 분류', section: 1 },
  { key: 'ingredients', ko: '전성분', section: 3 },
];

/** 칸이 채워졌나. 진행 표시·칸별 빈 안내에 쓴다. 최종 판정은 validateForm 이 한다 */
function filled(form: RegistrationForm, key: RequiredField): boolean {
  const v = form[key];
  if (key === 'price_krw') return v !== '' && Number(v) > 0;
  return typeof v === 'string' && v.trim().length > 0;
}

const FIELD_HELP: Record<RequiredField, string> = {
  product_name: '상품명을 적어 주세요',
  price_krw: '가격을 원 단위로 적어 주세요',
  secondary_category: '대분류를 골라 주세요',
  tertiary_category: '세부 분류를 골라 주세요',
  ingredients: '전성분을 붙여 넣어 주세요',
};

/**
 * 상품 등록 · 왼쪽은 계약 `product-registration-spec.md` 의 입력 필드, 오른쪽은
 * **실제 쇼핑몰 상세 페이지의 본문** 을 iframe 으로 띄운 미리보기다 (쇼핑몰이 `preview=1` 이면 헤더·로그인 같은
 * 사이트 껍데기를 빼고 상품 부분만 그린다, App.tsx).
 *
 * 폼이 바뀌면 초안을 localStorage 에 쓰고, 쇼핑몰(`/?product=DRAFT&preview=1`)이 storage
 * 이벤트로 그대로 다시 그린다. 미리보기용 컴포넌트를 따로 만들지 않는 이유는 그러면 언젠가
 * 둘이 달라지기 때문이다. 사장님이 본 것과 고객이 볼 것이 같은 코드여야 한다.
 *
 * 2026-09-21 개편 (유림님). 긴 폼 하나였던 것을 세 묶음(기본 정보 · 특징 태그 · 상세 설명)으로 나누고,
 * 빈 폼에 바로 뜨던 빨간 오류 목록을 없앴다 — 오류는 그 칸을 건드렸거나 등록을 눌렀을 때 **그 칸 밑에** 한 줄로.
 * 맨 위에 필수 5개 중 몇 개가 찼는지 보여 주고, 등록 버튼은 항상 누를 수 있게 두되 부족하면 첫 빈 칸으로 데려간다.
 * 대표 이미지는 끌어다 놓는 자리와 미리보기로. 가격 밑의 달러 환산 문구는 뗐다 — 고객 화면도 원화다.
 */
export default function RegisterScreen() {
  const mine = useRegistered();

  const [form, setForm] = useState<RegistrationForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<{ text: string; kind: 'ok' | 'warn' } | null>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  /** 건드린 칸. 오류는 건드린 칸이나 등록을 시도한 뒤에만 보인다 */
  const [touched, setTouched] = useState<Partial<Record<RequiredField, boolean>>>({});
  const [attempted, setAttempted] = useState(false);
  const [imageMode, setImageMode] = useState<'file' | 'url'>('file');
  const [dragOver, setDragOver] = useState(false);

  const { errors, warnings } = useMemo(() => validateForm(form), [form]);
  const tertiaries = CATEGORY_TREE.get(form.secondary_category) ?? [];
  const doneCount = REQUIRED.filter((r) => filled(form, r.key)).length;
  const showError = (key: RequiredField) => (attempted || touched[key]) && !filled(form, key);

  // 폼 → 초안. 디바운스해서 쇼핑몰 미리보기가 타자마다 다시 그리지 않게 한다
  useEffect(() => {
    const id = window.setTimeout(() => setDraft(form), DRAFT_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [form]);

  // 화면을 떠나면 초안을 지운다. 초안이 남아 있으면 쇼핑몰 목록 맨 앞에 계속 뜬다
  useEffect(() => () => setDraft(null), []);

  const set = <K extends keyof RegistrationForm>(key: K, value: RegistrationForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));
  const touch = (key: RequiredField) => setTouched((t) => (t[key] ? t : { ...t, [key]: true }));

  const toggleHighlight = (value: string) =>
    setForm((prev) => ({
      ...prev,
      highlights: prev.highlights.includes(value)
        ? prev.highlights.filter((h) => h !== value)
        : [...prev.highlights, value],
    }));

  const onImageFile = (file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setSavedMsg({ text: '이미지 파일만 올릴 수 있습니다.', kind: 'warn' });
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setSavedMsg({ text: `이미지가 ${Math.round(MAX_IMAGE_BYTES / 1024)}KB 를 넘습니다. 더 작은 파일을 골라 주세요.`, kind: 'warn' });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      set('image_url', String(reader.result ?? ''));
      setSavedMsg(null);
    };
    reader.readAsDataURL(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    onImageFile(e.dataTransfer.files?.[0] ?? null);
  };

  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (saving) return;
    if (errors.length) {
      // 부족한 칸을 전부 드러내고 첫 빈 칸으로 데려간다. 버튼을 잠가 두면 왜 안 되는지 알 길이 없다
      setAttempted(true);
      const first = REQUIRED.find((r) => !filled(form, r.key));
      if (first) {
        const el = document.getElementById(`reg-${first.key}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        (el as HTMLElement | null)?.focus?.();
      }
      return;
    }
    setSaving(true);
    try {
      const r = await registerProduct(form, editingId ?? undefined);
      if (r.mode === 'backend') {
        setSavedMsg({
          text: `${r.product.product_name} 을(를) 쇼핑몰에 등록했습니다.${r.activated ? ' 쇼핑몰에 바로 보입니다.' : ' 운영자 승인이 끝나면 쇼핑몰에 보입니다.'}`,
          kind: 'ok',
        });
      } else {
        setSavedMsg({
          text: editingId
            ? `${r.product.product_name} 을(를) 수정했습니다. 수정 내용은 지금 이 브라우저에서만 보입니다.`
            : `${r.product.product_name} 을(를) 쇼핑몰에 올리지 못해 이 브라우저에만 저장했습니다. 잠시 뒤 다시 등록해 주세요.`,
          kind: 'warn',
        });
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
      setTouched({});
      setAttempted(false);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setTouched({});
    setAttempted(false);
    setSavedMsg(null);
  };

  const edit = (id: string) => {
    const r = mine.find((m) => m.product.product_id === id);
    if (!r) return;
    setForm(fromProduct(r.product));
    setEditingId(id);
    setSavedMsg(null);
    setTouched({});
    setAttempted(false);
    setPreviewKey((k) => k + 1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const previewSrc = `/?product=${DRAFT_PRODUCT_ID}&preview=1`;
  const missing = REQUIRED.filter((r) => !filled(form, r.key));
  const priceKrw = form.price_krw === '' ? null : Number(form.price_krw);

  return (
    <div className="stack">
      <div className="register">
        <div className="register__form">
          {/* 진행 표시. 필수 5개 중 몇 개가 찼나 — 긴 폼에서 "얼마나 남았지" 를 한눈에 */}
          <div className="reg-progress" role="status">
            <div className="reg-progress__bar" aria-hidden="true">
              <span style={{ width: `${(doneCount / REQUIRED.length) * 100}%` }} />
            </div>
            <p className="reg-progress__text">
              {editingId ? <b>상품 수정 중</b> : <b>새 상품</b>}
              {' · '}
              필수 {REQUIRED.length}개 중 <b>{doneCount}개</b> 채움
              {missing.length > 0 ? <span className="reg-progress__missing"> · 남은 것: {missing.map((m) => m.ko).join(', ')}</span> : <span className="reg-progress__done"> · 등록할 수 있습니다</span>}
            </p>
          </div>

          {savedMsg ? (
            <div className={`reg-toast reg-toast--${savedMsg.kind}`} role="status">
              <span>{savedMsg.text}</span>
              <button type="button" className="reg-toast__close" aria-label="닫기" onClick={() => setSavedMsg(null)}>×</button>
            </div>
          ) : null}

          {/* ① 기본 정보 */}
          <section className="reg-section" aria-labelledby="reg-sec-1">
            <header className="reg-section__head">
              <span className="reg-section__num">1</span>
              <div>
                <h3 id="reg-sec-1">기본 정보</h3>
                <p>목록 카드와 상세 맨 위에 보이는 것들입니다</p>
              </div>
            </header>

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-product_name">상품명 <em className="reg-req">필수</em></label>
              <input
                id="reg-product_name"
                className={`reg-input${showError('product_name') ? ' is-invalid' : ''}`}
                value={form.product_name}
                onChange={(e) => set('product_name', e.target.value)}
                onBlur={() => touch('product_name')}
                placeholder="예: 진정 수분 세럼"
                maxLength={80}
                aria-invalid={showError('product_name')}
              />
              {showError('product_name') ? <p className="reg-error">{FIELD_HELP.product_name}</p> : null}
            </div>

            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-price_krw">가격 <em className="reg-req">필수</em></label>
                <div className={`reg-input reg-input--unit${showError('price_krw') ? ' is-invalid' : ''}`}>
                  <input
                    id="reg-price_krw"
                    type="number"
                    min={0}
                    step={100}
                    inputMode="numeric"
                    value={form.price_krw}
                    onChange={(e) => set('price_krw', e.target.value === '' ? '' : Number(e.target.value))}
                    onBlur={() => touch('price_krw')}
                    placeholder="32000"
                    aria-invalid={showError('price_krw')}
                  />
                  <span>원</span>
                </div>
                {showError('price_krw') ? (
                  <p className="reg-error">{FIELD_HELP.price_krw}</p>
                ) : priceKrw && priceKrw > 0 ? (
                  <p className="reg-hint">
                    고객 화면에 <b>{priceKrw.toLocaleString('ko-KR')}원</b> 으로 보입니다 · 추천에서는 {recommendPriceBin(priceKrw).bin} 가격대로 묶입니다
                  </p>
                ) : null}
              </div>
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-brand">브랜드</label>
                <input id="reg-brand" className="reg-input" value={form.brand_name} readOnly />
                <p className="reg-hint">로그인한 브랜드로 등록됩니다</p>
              </div>
            </div>

            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-secondary_category">대분류 <em className="reg-req">필수</em></label>
                <select
                  id="reg-secondary_category"
                  className={`reg-input${showError('secondary_category') ? ' is-invalid' : ''}`}
                  value={form.secondary_category}
                  onChange={(e) => {
                    set('secondary_category', e.target.value);
                    set('tertiary_category', '');
                    touch('secondary_category');
                  }}
                  onBlur={() => touch('secondary_category')}
                  aria-invalid={showError('secondary_category')}
                >
                  <option value="">골라 주세요</option>
                  {SECONDARY_CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.ko}</option>
                  ))}
                </select>
                {showError('secondary_category') ? <p className="reg-error">{FIELD_HELP.secondary_category}</p> : null}
              </div>
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-tertiary_category">세부 분류 <em className="reg-req">필수</em></label>
                <select
                  id="reg-tertiary_category"
                  className={`reg-input${showError('tertiary_category') ? ' is-invalid' : ''}`}
                  value={form.tertiary_category}
                  disabled={!form.secondary_category}
                  onChange={(e) => {
                    set('tertiary_category', e.target.value);
                    touch('tertiary_category');
                  }}
                  onBlur={() => touch('tertiary_category')}
                  aria-invalid={showError('tertiary_category')}
                >
                  <option value="">{form.secondary_category ? '골라 주세요' : '대분류를 먼저 고르세요'}</option>
                  {tertiaries.map((t) => (
                    <option key={t} value={t}>{labelKo(t)}</option>
                  ))}
                </select>
                {showError('tertiary_category') ? <p className="reg-error">{FIELD_HELP.tertiary_category}</p> : null}
              </div>
            </div>

            <div className="reg-row">
              <div className="reg-field">
                <label className="reg-label" htmlFor="reg-size">용량</label>
                <input id="reg-size" className="reg-input" value={form.size} onChange={(e) => set('size', e.target.value)} placeholder="50ml" maxLength={30} />
              </div>
            </div>

            <div className="reg-field">
              <span className="reg-label">
                대표 이미지
                <span className="reg-segment" role="tablist" aria-label="이미지 넣는 방법">
                  <button type="button" role="tab" aria-selected={imageMode === 'file'} className={imageMode === 'file' ? 'is-on' : ''} onClick={() => setImageMode('file')}>파일 올리기</button>
                  <button type="button" role="tab" aria-selected={imageMode === 'url'} className={imageMode === 'url' ? 'is-on' : ''} onClick={() => setImageMode('url')}>이미지 주소</button>
                </span>
              </span>
              {imageMode === 'file' ? (
                <div
                  className={`reg-drop${dragOver ? ' is-over' : ''}${form.image_url ? ' has-image' : ''}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                >
                  {form.image_url ? (
                    <img className="reg-drop__preview" src={form.image_url} alt="대표 이미지 미리보기" />
                  ) : (
                    <div className="reg-drop__icon" aria-hidden="true">＋</div>
                  )}
                  <div className="reg-drop__body">
                    <p className="reg-drop__title">{form.image_url ? '이미지가 들어갔습니다' : '이미지를 여기로 끌어다 놓거나'}</p>
                    <label className="reg-drop__pick">
                      {form.image_url ? '다른 파일로 바꾸기' : '파일 고르기'}
                      <input type="file" accept="image/*" onChange={(e) => onImageFile(e.target.files?.[0] ?? null)} />
                    </label>
                    <p className="reg-hint">JPG·PNG·WebP · {Math.round(MAX_IMAGE_BYTES / 1024)}KB 이하 · 정사각형이 가장 잘 나옵니다</p>
                    {form.image_url ? (
                      <button type="button" className="reg-link" onClick={() => set('image_url', '')}>지우기</button>
                    ) : null}
                  </div>
                </div>
              ) : (
                <>
                  <input
                    className="reg-input"
                    value={form.image_url.startsWith('data:') ? '' : form.image_url}
                    onChange={(e) => set('image_url', e.target.value)}
                    placeholder="https:// 로 시작하는 이미지 주소"
                  />
                  {form.image_url && !form.image_url.startsWith('data:') ? <img className="reg-url-preview" src={form.image_url} alt="대표 이미지 미리보기" /> : null}
                </>
              )}
            </div>
          </section>

          {/* ② 특징 태그 */}
          <section className="reg-section" aria-labelledby="reg-sec-2">
            <header className="reg-section__head">
              <span className="reg-section__num">2</span>
              <div>
                <h3 id="reg-sec-2">상품 특징</h3>
                <p>추천이 이 태그를 봅니다. 해당하는 것을 모두 고르세요 · 고른 것 <b>{form.highlights.length}개</b></p>
              </div>
            </header>
            {HIGHLIGHT_GROUPS.map((g) => {
              const picked = g.options.filter((o) => form.highlights.includes(o.value)).length;
              return (
                <div className="reg-field" key={g.group}>
                  <span className="reg-label">
                    {g.ko}
                    {picked > 0 ? <span className="reg-count">{picked}</span> : null}
                    <span className="reg-hint-inline">{g.hint}</span>
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
              );
            })}
            {form.highlights.length === 0 ? <p className="reg-note">태그가 하나도 없으면 추천에 잘 안 뜹니다. 피부 고민은 꼭 골라 주세요.</p> : null}
          </section>

          {/* ③ 상세 설명 */}
          <section className="reg-section" aria-labelledby="reg-sec-3">
            <header className="reg-section__head">
              <span className="reg-section__num">3</span>
              <div>
                <h3 id="reg-sec-3">상세 설명</h3>
                <p>상세 페이지 본문입니다. 전성분만 필수, 나머지는 있으면 좋습니다</p>
              </div>
            </header>

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-ingredients">전성분 <em className="reg-req">필수</em></label>
              <textarea
                id="reg-ingredients"
                className={`reg-input reg-textarea${showError('ingredients') ? ' is-invalid' : ''}`}
                rows={4}
                value={form.ingredients}
                onChange={(e) => set('ingredients', e.target.value)}
                onBlur={() => touch('ingredients')}
                placeholder="정제수, 글리세린, 나이아신아마이드, 병풀추출물 … (함량 순서대로, 한글·영문 모두 됩니다)"
                aria-invalid={showError('ingredients')}
              />
              {showError('ingredients') ? (
                <p className="reg-error">{FIELD_HELP.ingredients}</p>
              ) : (
                <p className="reg-hint">추천은 전성분의 순서를 보고 주요 성분을 읽습니다. 성분을 따로 고를 필요는 없습니다.</p>
              )}
            </div>

            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-what">이 제품은</label>
              <textarea id="reg-what" className="reg-input reg-textarea" rows={3} value={form.what_it_is} onChange={(e) => set('what_it_is', e.target.value)} placeholder="어떤 피부의 어떤 고민을 위해 만든 제품인지 한 문단" />
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-hi">앞세울 성분</label>
              <textarea id="reg-hi" className="reg-input reg-textarea" rows={3} value={form.highlighted_ingredients} onChange={(e) => set('highlighted_ingredients', e.target.value)} placeholder={'줄마다 "성분: 설명"\n병풀추출물: 각질 제거 후 진정\n나이아신아마이드: 톤과 결 정돈'} />
              <p className="reg-hint">상세 페이지에 보여 주는 용도입니다. 추천에는 반영되지 않습니다.</p>
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-callout">성분 안내</label>
              <input id="reg-callout" className="reg-input" value={form.ingredient_callouts} onChange={(e) => set('ingredient_callouts', e.target.value)} placeholder="파라벤 무첨가. 향료 포함" />
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-usage">사용법</label>
              <textarea id="reg-usage" className="reg-input reg-textarea" rows={3} value={form.suggested_usage} onChange={(e) => set('suggested_usage', e.target.value)} placeholder="토너 후 2~3방울을 …" />
            </div>
            <div className="reg-field">
              <label className="reg-label" htmlFor="reg-story">브랜드 이야기</label>
              <textarea id="reg-story" className="reg-input reg-textarea" rows={3} value={form.brand_story} onChange={(e) => set('brand_story', e.target.value)} placeholder="왜 이 브랜드를 만들었는지. 고객이 의견을 남길 때 보는 자리입니다" />
            </div>
          </section>

          {/* 등록 줄. 아래에 붙어 따라온다 — 긴 폼 끝까지 내려가지 않아도 상태가 보인다 */}
          <div className="reg-sticky">
            <div className="reg-sticky__status">
              {attempted && errors.length ? (
                <span className="reg-sticky__error">아직 못 채운 필수 항목: {missing.map((m) => m.ko).join(', ')}</span>
              ) : warnings.length ? (
                <span className="reg-sticky__warn" title={warnings.join('\n')}>{warnings[0]}</span>
              ) : (
                <span className="reg-sticky__ok">{missing.length === 0 ? '등록할 준비가 됐습니다' : `필수 ${missing.length}개가 남았습니다`}</span>
              )}
            </div>
            <div className="reg-sticky__actions">
              {editingId ? (
                <button type="button" className="reg-btn reg-btn--ghost" onClick={reset}>취소</button>
              ) : null}
              <button type="button" className="reg-btn reg-btn--primary" onClick={() => void save()} disabled={saving} aria-disabled={errors.length > 0}>
                {saving ? '등록 중…' : editingId ? '수정 저장' : '쇼핑몰에 등록'}
              </button>
            </div>
          </div>

          <Panel title="등록한 상품" aside={`${mine.length}개`}>
            {mine.length === 0 ? (
              <p className="reg-empty">아직 등록한 상품이 없습니다. 위에서 등록하면 쇼핑몰 목록과 추천 후보에 바로 들어갑니다.</p>
            ) : (
              <ul className="reg-list">
                {mine.map((r) => (
                  <li key={r.product.product_id} className="reg-list__item">
                    {r.product.image_url ? <img className="reg-list__thumb" src={r.product.image_url} alt="" /> : <span className="reg-list__thumb reg-list__thumb--empty" aria-hidden="true" />}
                    <span className="reg-list__name">{r.product.product_name}</span>
                    <span className="reg-list__meta">
                      {labelKo(r.product.category[2] ?? r.product.category[1] ?? '')} · {(r.product.price_krw ?? Math.round(r.product.price_usd * KRW_PER_USD)).toLocaleString('ko-KR')}원 · {r.updated_at.slice(0, 10)} 저장
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
            <div>
              <strong>고객이 보게 될 화면</strong>
              <span>왼쪽에 입력하면 바로 바뀝니다</span>
            </div>
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
