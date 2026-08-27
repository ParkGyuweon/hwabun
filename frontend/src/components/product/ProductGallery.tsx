import { useState } from 'react';
import { track } from '../../lib/logger';

const PLACEHOLDER = '/images/product-placeholder.svg';
const THUMB_COUNT = 4;

interface ProductGalleryProps {
  /** 데이터셋에 이미지가 없어 현재는 항상 null 이 들어온다 */
  imageUrl: string | null;
  productName: string;
  productId: string;
}

/**
 * 세포라 상세 페이지 좌측 갤러리.
 *
 * 이미지가 확보되면 imageUrl 만 채우면 되도록 썸네일 자리까지 미리 잡아둔다.
 * 파일명은 product_id 기준으로 받기로 데이터 담당자와 이야기 중이다.
 */
export default function ProductGallery({ imageUrl, productName, productId }: ProductGalleryProps) {
  const [failed, setFailed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const src = !imageUrl || failed ? PLACEHOLDER : imageUrl;

  const selectThumb = (index: number) => {
    setActiveIndex(index);
    track('media_view', { product_id: productId, media_index: index, media_type: 'image' });
  };

  return (
    <div className="gallery">
      <div className="gallery__main">
        <img src={src} alt={productName} onError={() => setFailed(true)} />
        {!imageUrl ? <span className="gallery__badge">이미지 확보 전</span> : null}
      </div>

      <ul className="gallery__thumbs" aria-label="추가 이미지">
        {Array.from({ length: THUMB_COUNT }, (_, index) => (
          <li key={index}>
            <button
              type="button"
              className={activeIndex === index ? 'is-active' : ''}
              data-log-action="media_view"
              aria-label={`이미지 ${index + 1} 보기`}
              onClick={() => selectThumb(index)}
            >
              <img src={PLACEHOLDER} alt="" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
