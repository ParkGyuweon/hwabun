import { useEffect, useMemo, useState } from 'react';
import { IMAGE_WIDTH_MAIN, IMAGE_WIDTH_THUMB, sizedImage } from '../../lib/image';
import { track } from '../../lib/logger';

const PLACEHOLDER = '/images/product-placeholder.svg';
/** 이미지가 없는 상품에서도 레이아웃이 무너지지 않도록 유지하는 최소 썸네일 칸 수 */
const MIN_THUMB_SLOTS = 4;

interface ProductGalleryProps {
  imageUrl: string | null;
  /** 대표 이미지 뒤에 붙는 추가 이미지 */
  images: string[];
  productName: string;
  productId: string;
}

/**
 * 세포라 상세 페이지 좌측 갤러리.
 *
 * 대표 이미지와 추가 이미지를 한 배열로 합쳐 썸네일과 메인 뷰를 함께 굴린다.
 */
export default function ProductGallery({ imageUrl, images, productName, productId }: ProductGalleryProps) {
  const [failedSrc, setFailedSrc] = useState<Set<string>>(new Set());
  const [activeIndex, setActiveIndex] = useState(0);

  const gallery = useMemo(
    () => [imageUrl, ...images].filter((src): src is string => Boolean(src)),
    [imageUrl, images],
  );

  // 상품이 바뀌면 첫 이미지부터 다시 본다
  useEffect(() => {
    setActiveIndex(0);
    setFailedSrc(new Set());
  }, [productId]);

  const activeSrc = gallery[activeIndex] ?? null;
  const mainSrc = !activeSrc || failedSrc.has(activeSrc) ? PLACEHOLDER : activeSrc;

  const markFailed = (src: string) => {
    setFailedSrc((prev) => new Set(prev).add(src));
  };

  const selectThumb = (index: number) => {
    setActiveIndex(index);
    track('media_view', { product_id: productId, media_index: index, media_type: 'image' });
  };

  const slotCount = Math.max(gallery.length, MIN_THUMB_SLOTS);

  return (
    <div className="gallery" data-log-content="product_image">
      <div className="gallery__main">
        <img
          src={sizedImage(mainSrc, IMAGE_WIDTH_MAIN) ?? PLACEHOLDER}
          alt={productName}
          onError={() => activeSrc && markFailed(activeSrc)}
        />
        {gallery.length === 0 ? <span className="gallery__badge">이미지 확보 전</span> : null}
      </div>

      <ul className="gallery__thumbs" aria-label="추가 이미지">
        {Array.from({ length: slotCount }, (_, index) => {
          const src = gallery[index];
          const thumbSrc = !src || failedSrc.has(src) ? PLACEHOLDER : src;

          return (
            <li key={index}>
              <button
                type="button"
                className={activeIndex === index ? 'is-active' : ''}
                data-log-action="media_view"
                aria-label={`이미지 ${index + 1} 보기`}
                disabled={!src}
                onClick={() => selectThumb(index)}
              >
                <img
                  src={sizedImage(thumbSrc, IMAGE_WIDTH_THUMB) ?? PLACEHOLDER}
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                  onError={() => src && markFailed(src)}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
