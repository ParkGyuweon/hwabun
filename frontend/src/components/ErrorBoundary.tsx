import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  failed: boolean;
}

/**
 * 화면 그리기 중 오류가 나도 흰 화면으로 끝나지 않게 막는다 (2026-09-29).
 * 오류는 콘솔에 남기고, 사용자에게는 짧은 문장과 새로고침 버튼만 보인다.
 * 발표용 상단 띠(DemoBanner)는 이 경계 밖에 두어 오류가 나도 계속 보인다.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          minHeight: '60vh',
          padding: 24,
          textAlign: 'center',
          fontSize: 16,
        }}
      >
        <p style={{ margin: 0 }}>화면을 불러오지 못했어요.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          style={{ padding: '10px 20px', fontSize: 15, borderRadius: 8, border: '1px solid #ccc', background: '#fff', color: '#222', cursor: 'pointer' }}
        >
          새로고침
        </button>
      </div>
    );
  }
}
