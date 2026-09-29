import LegalDocument from '../components/legal/LegalDocument';
import type { LegalSection } from '../components/legal/LegalDocument';

export const PRIVACY_VERSION = 'v1';
export const PRIVACY_EFFECTIVE_DATE = '2026-09-29';

/*
 * 이 방침은 코드가 실제로 하는 일과 맞아야 한다. 수집 항목을 늘리거나 줄이면 여기도 같이 고친다.
 *   회원 정보            lib/auth · components/auth (가입 폼) · lib/memberProfile (피부 정보)
 *   행동 기록            lib/logger (브라우저 단위 세션 식별값은 sessionStorage)
 *   결제                 lib/payment (PortOne 에 이름·이메일 전달)
 *   브라우저 저장소      lib/auth (localStorage) · lib/wishlist · lib/logger (sessionStorage)
 */
const sections: LegalSection[] = [
  {
    id: 'privacy-items',
    title: '1. 모으는 정보',
    body: (
      <>
        <h3>회원가입</h3>
        <ul>
          <li>
            <strong>필수</strong> 이메일, 비밀번호, 닉네임. 비밀번호는 알아볼 수 없게 암호화해서 저장합니다.
          </li>
          <li>
            <strong>선택</strong> 피부 타입, 피부 톤, 머리색, 눈색. 나에게 맞는 상품을 추천하는 데 씁니다. 입력하지 않아도
            이용할 수 있습니다.
          </li>
        </ul>

        <h3>주문과 결제</h3>
        <ul>
          <li>주문 내역, 결제 금액, 결제 대행사가 발급한 거래번호</li>
        </ul>

        <h3>서비스 이용 기록</h3>
        <ul>
          <li>방문한 화면, 본 상품, 스크롤한 정도와 머문 시간, 누른 버튼과 링크</li>
          <li>찜, 장바구니 담기·빼기, 구매 같은 쇼핑 행동</li>
        </ul>
        <p>
          로그인하지 않아도 브라우저마다 붙는 임시 식별값으로 기록을 모읍니다. 가입할 때 ‘둘러본 기록을 내 계정과
          연결’에 동의한 회원은 로그인한 뒤의 기록이 계정과 연결되고, 동의하지 않은 회원의 기록은 계정 없이 모읍니다.
        </p>
        <p>
          화면에서 선택하거나 복사한 글의 내용은 모으지 않습니다. 접속 IP와 기기 정보도 화면에서 따로 모으지 않습니다.
          다만 웹서버의 접속 기록에는 접속한 IP가 남을 수 있습니다.
        </p>

        <h3>리뷰와 의견</h3>
        <ul>
          <li>작성한 리뷰와 의견의 내용, 작성 시각</li>
        </ul>
      </>
    ),
  },
  {
    id: 'privacy-purpose',
    title: '2. 정보를 쓰는 곳',
    body: (
      <ul>
        <li>회원 확인과 로그인 유지</li>
        <li>주문 처리와 결제 확인</li>
        <li>둘러본 기록과 피부 정보를 바탕으로 한 맞춤 상품 추천</li>
        <li>
          입점 브랜드에 제공하는 통계. 여러 고객의 기록을 묶어서 만든 숫자만 제공하며,{' '}
          <strong>누구인지 알아볼 수 있는 형태로 브랜드에 넘기지 않습니다.</strong>
        </li>
        <li>
          리뷰를 보여줄 때 작성자가 쓴 당시의 피부 정보(피부 타입 등)를 함께 표시합니다. 비슷한 피부의 고객이 참고할 수
          있게 하기 위해서입니다.
        </li>
      </ul>
    ),
  },
  {
    id: 'privacy-outsourcing',
    title: '3. 다른 곳에 맡기는 일',
    body: (
      <>
        <table className="legal__table">
          <thead>
            <tr>
              <th scope="col">맡는 곳</th>
              <th scope="col">하는 일</th>
              <th scope="col">넘기는 정보</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>PortOne</td>
              <td>결제 처리</td>
              <td>이름(닉네임), 이메일, 주문 번호, 결제 금액</td>
            </tr>
            <tr>
              <td>OpenAI (SSAFY GMS 경유)</td>
              <td>고객이 남긴 의견을 주제별로 분류</td>
              <td>의견 본문</td>
            </tr>
          </tbody>
        </table>
        <p>고객이 남긴 의견 본문은 분류를 위해 외부 AI 서비스에 전달될 수 있습니다.</p>
      </>
    ),
  },
  {
    id: 'privacy-retention',
    title: '4. 보관 기간과 파기',
    body: (
      <>
        <p>회원이 탈퇴하거나 모은 목적을 다 이루면 정보를 지체 없이 지웁니다.</p>
        <ul>
          <li>
            <strong>탈퇴하면 이메일, 닉네임, 피부 정보는 바로 지웁니다.</strong>
          </li>
          <li>
            <strong>주문·정산 기록은 전자상거래법에 따라 5년 동안 보관합니다.</strong>
          </li>
          <li>
            서비스 이용 기록은 회원을 알아볼 수 있는 정보와 떼어 낸 상태로 통계와 추천 품질을 높이는 데에만 쓰고, <strong>1년</strong>이
            지나면 지웁니다.
          </li>
          <li>작성한 리뷰는 지워지지 않고 작성자가 “탈퇴한 회원”으로 표시되어 남습니다.</li>
          <li>보관 기간이 지난 기록은 한 달에 한 번 모아서 지웁니다.</li>
        </ul>
      </>
    ),
  },
  {
    id: 'privacy-rights',
    title: '5. 이용자의 권리',
    body: (
      <ul>
        <li>
          <strong>열람·정정</strong> 마이페이지의 내 정보에서 언제든지 보고 고칠 수 있습니다.
        </li>
        <li>
          <strong>동의 철회·탈퇴</strong> 마이페이지에서 회원 탈퇴를 하면 동의를 거두게 됩니다.
        </li>
        <li>
          <strong>문의</strong> 프로젝트 팀 문의 (시연용). 이 쇼핑몰은 학습용 프로젝트라 별도 고객센터를 운영하지
          않습니다.
        </li>
      </ul>
    ),
  },
  {
    id: 'privacy-storage',
    title: '6. 쿠키와 브라우저 저장소',
    body: (
      <>
        <p>편하게 이용할 수 있도록 다음 값을 이용자의 브라우저에 저장합니다.</p>
        <ul>
          <li>로그인 상태</li>
          <li>찜 목록과 장바구니</li>
          <li>이용 기록을 한 번의 방문으로 묶기 위한 세션 식별값</li>
          <li>이 안내를 확인했는지 여부</li>
        </ul>
        <p>브라우저 설정에서 저장된 값을 지울 수 있습니다. 지우면 로그인이 풀리고 찜·장바구니가 비워질 수 있습니다.</p>
      </>
    ),
  },
  {
    id: 'privacy-change',
    title: '7. 방침 변경',
    body: <p>이 방침을 바꿀 때는 바뀐 내용과 적용 날짜를 쇼핑몰 화면에 미리 알립니다.</p>,
  },
];

export default function PrivacyPage() {
  return (
    <LegalDocument
      title="개인정보처리방침"
      version={PRIVACY_VERSION}
      effectiveDate={PRIVACY_EFFECTIVE_DATE}
      intro={
        <p>
          BLOOM은 SSAFY 15기 프로젝트 시연용 쇼핑몰입니다. 어떤 정보를 왜 모으고 어떻게 다루는지 아래에 적었습니다.
        </p>
      }
      sections={sections}
    />
  );
}
