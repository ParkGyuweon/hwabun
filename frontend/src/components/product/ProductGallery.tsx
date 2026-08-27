import { useState } from 'react';

const PLACEHOLDER = '/images/product-placeholder.svg';

interface ProductGalleryProps {
  /** 데이터셋에 이미지가 없어 현재는 항상 null 이 들어온다 */
  imageUrl: string | null;
  productName: string;
}

/**
 * 세포라 상세 페이지의 좌측 갤러리 영역.
 *
 * 이미지가 확보되면 imageUrl 만 채우면 되도록 썸네일 자리까지 미리 잡아둔다.
 */
export default function ProductGallery({ imageUrl, productName }: ProductGalleryProps) {
  const [failed, setFailed] = useState(false);
  const src = !imageUrl || failed ? PLACEHOLDER : imageUrl;

  return (
    <div className="gallery">
      <div className="gallery__main">
        <img src={src} alt={productName} onError={() => setFailed(true)} />
        {!imageUrl ? <span className="gallery__badge">이미지 확보 전</span> : null}
      </div>
      <ul className="gallery__thumbs" aria-label="추가 이미지">
        {[0, 1, 2, 3].map((index) => (
          <li key={index}>
            <img src={PLACEHOLDER} alt="" aria-hidden="true" />
          </li>
        ))}
      </ul>
    </div>
  );
}
