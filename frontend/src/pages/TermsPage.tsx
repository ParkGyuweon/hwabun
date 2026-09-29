import LegalDocument from '../components/legal/LegalDocument';
import type { LegalSection } from '../components/legal/LegalDocument';

export const TERMS_VERSION = 'v1';
export const TERMS_EFFECTIVE_DATE = '2026-09-29';

const sections: LegalSection[] = [
  {
    id: 'terms-purpose',
    title: '제1조 목적',
    body: (
      <p>
        이 약관은 BLOOM(이하 “쇼핑몰”)을 이용할 때 쇼핑몰과 이용자 사이의 권리와 의무를 정합니다. BLOOM은 SSAFY 15기
        프로젝트 팀이 시연을 위해 만든 쇼핑몰이며, 실제로 상품을 판매하지 않습니다.
      </p>
    ),
  },
  {
    id: 'terms-signup',
    title: '제2조 회원가입',
    body: (
      <ul>
        <li>이메일, 비밀번호, 닉네임을 입력하고 이 약관과 개인정보처리방침에 동의하면 회원이 됩니다.</li>
        <li>다른 사람의 정보를 쓰거나 사실과 다른 정보를 입력하면 가입을 거절하거나 이용을 제한할 수 있습니다.</li>
        <li>피부 타입·피부 톤 같은 정보는 입력하지 않아도 가입하고 이용할 수 있습니다.</li>
      </ul>
    ),
  },
  {
    id: 'terms-withdraw',
    title: '제3조 회원 탈퇴',
    body: (
      <ul>
        <li>회원은 언제든지 마이페이지에서 탈퇴할 수 있습니다.</li>
        <li>탈퇴하면 계정 정보는 개인정보처리방침에 따라 처리합니다. 작성한 리뷰는 “탈퇴한 회원”으로 표시되어 남습니다.</li>
      </ul>
    ),
  },
  {
    id: 'terms-order',
    title: '제4조 주문과 결제',
    body: (
      <ul>
        <li>쇼핑몰의 주문과 결제는 시연을 위한 것입니다. 상품은 배송되지 않습니다.</li>
        <li>
          결제는 결제 대행사의 <strong>테스트 결제</strong>로 진행되며 실제로 돈이 청구되지 않습니다. 결제창에 실제 카드나
          계좌 정보를 입력하지 마세요.
        </li>
        <li>화면에 보이는 가격·할인·재고는 시연용 값이며 실제 판매 조건이 아닙니다.</li>
      </ul>
    ),
  },
  {
    id: 'terms-duty',
    title: '제5조 이용자가 지킬 일',
    body: (
      <ul>
        <li>다른 사람의 계정을 쓰거나 서비스 운영을 방해하지 않습니다.</li>
        <li>리뷰와 의견에 욕설, 광고, 다른 사람의 개인정보를 올리지 않습니다. 이런 글은 알리지 않고 가릴 수 있습니다.</li>
      </ul>
    ),
  },
  {
    id: 'terms-liability',
    title: '제6조 책임의 한계',
    body: (
      <ul>
        <li>쇼핑몰은 학습용 프로젝트로 운영되어, 예고 없이 서비스가 멈추거나 데이터가 초기화될 수 있습니다.</li>
        <li>상품 정보와 추천은 참고용이며, 그 내용이 정확하거나 이용자에게 맞는다고 보장하지 않습니다.</li>
        <li>쇼핑몰의 고의나 중대한 잘못이 없는 한, 서비스 이용으로 생긴 손해에 대해 책임지지 않습니다.</li>
      </ul>
    ),
  },
  {
    id: 'terms-change',
    title: '제7조 약관 변경',
    body: (
      <p>
        약관을 바꿀 때는 바뀐 내용과 적용 날짜를 쇼핑몰 화면에 미리 알립니다. 바뀐 약관에 동의하지 않으면 탈퇴할 수
        있습니다.
      </p>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalDocument
      title="이용약관"
      version={TERMS_VERSION}
      effectiveDate={TERMS_EFFECTIVE_DATE}
      intro={<p>BLOOM은 SSAFY 15기 프로젝트 시연용 쇼핑몰입니다. 실제로 판매하거나 결제하지 않습니다.</p>}
      sections={sections}
    />
  );
}
