import type { ReactNode } from "react";

type IconProps = { size?: number; children: ReactNode };
const Icon = ({ size = 18, children }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);

export const FlowIcon = () => <Icon><path d="M4 6h5a3 3 0 0 1 3 3v6a3 3 0 0 0 3 3h5"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="18" r="2"/><circle cx="12" cy="12" r="2"/></Icon>;
export const UploadIcon = () => <Icon><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M5 14v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5"/></Icon>;
export const ChartIcon = () => <Icon><path d="M4 20V10m6 10V4m6 16v-7m4 7H2"/></Icon>;
export const KeyIcon = () => <Icon><circle cx="8" cy="15" r="4"/><path d="m11 12 8-8m-3 3 2 2"/></Icon>;
export const SearchIcon = () => <Icon><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></Icon>;
export const FileIcon = () => <Icon><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5M9 12h6m-6 4h6"/></Icon>;
export const CheckIcon = () => <Icon size={16}><path d="m5 12 4 4L19 6"/></Icon>;
export const ArrowIcon = () => <Icon size={16}><path d="m9 18 6-6-6-6"/></Icon>;
export const RefreshIcon = () => <Icon size={16}><path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/></Icon>;
