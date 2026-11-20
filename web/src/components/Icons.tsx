import type { ReactElement } from 'react';

// Small inline icons. Decorative: always paired with a word by the caller.
interface IconProps {
  size?: number;
  className?: string;
}

function svg(props: IconProps, children: ReactElement): ReactElement {
  const size = props.size ?? 16;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={props.className}
    >
      {children}
    </svg>
  );
}

export const CheckIcon = (p: IconProps): ReactElement => svg(p, <path d="M20 6 9 17l-5-5" />);
export const WarnIcon = (p: IconProps): ReactElement =>
  svg(p, <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>);
export const ErrorIcon = (p: IconProps): ReactElement =>
  svg(p, <><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" /></>);
export const WorkingIcon = (p: IconProps): ReactElement =>
  svg(p, <><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></>);
export const DashIcon = (p: IconProps): ReactElement => svg(p, <path d="M5 12h14" />);
export const PlusIcon = (p: IconProps): ReactElement => svg(p, <path d="M12 5v14M5 12h14" />);
export const ArrowUpIcon = (p: IconProps): ReactElement => svg(p, <path d="M12 19V5M5 12l7-7 7 7" />);
export const StopIcon = (p: IconProps): ReactElement => svg(p, <rect x="6" y="6" width="12" height="12" rx="2" />);
export const ChevronIcon = (p: IconProps): ReactElement => svg(p, <path d="m6 9 6 6 6-6" />);
export const MenuIcon = (p: IconProps): ReactElement => svg(p, <path d="M3 6h18M3 12h18M3 18h18" />);
