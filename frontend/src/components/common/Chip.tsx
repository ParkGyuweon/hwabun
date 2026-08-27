import type { ReactNode } from 'react';

interface ChipProps {
  children: ReactNode;
  tone?: 'default' | 'accent' | 'muted';
}

export default function Chip({ children, tone = 'default' }: ChipProps) {
  return <span className={`chip chip--${tone}`}>{children}</span>;
}
