import type { ReactElement, ReactNode } from 'react';

interface NoticeProps {
  tone?: 'default' | 'error' | 'warning';
  /** `alert` for failures, `status` for polite updates. */
  role?: 'alert' | 'status' | 'none';
  children: ReactNode;
  className?: string;
}

export function Notice({ tone = 'default', role = 'status', children, className }: NoticeProps): ReactElement {
  const cls = ['notice', tone === 'error' ? 'notice-error' : '', tone === 'warning' ? 'notice-warning' : '', className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <div className={cls} role={role === 'none' ? undefined : role}>
      {children}
    </div>
  );
}
