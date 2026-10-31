'use client';

import Link from 'next/link';
import type { MouseEventHandler, ReactNode } from 'react';
import BrandLogo from './brand-logo';
import { AccountMenu } from './account-menu';
import { ReturnLink } from './navigation-return';

type NavigationProps = {
  label?: string;
  fallback?: string;
  returnHref?: string;
  onNavigate?: MouseEventHandler<HTMLAnchorElement>;
  children?: ReactNode;
  account?: ReactNode;
  accountClassName?: string;
  accountTour?: string;
  afterAccount?: ReactNode;
};

export function WorkbenchNavigation({
  label,
  fallback,
  returnHref,
  onNavigate,
  children,
  account,
  accountClassName,
  accountTour,
  afterAccount,
  className = 'nav-links',
}: NavigationProps & { className?: string }) {
  return (
    <nav className={className} aria-label={label}>
      <ReturnLink href={returnHref} fallback={fallback} onClick={onNavigate} />
      {children}
      {account === undefined ? <AccountMenu className={accountClassName} tour={accountTour} /> : account}
      {afterAccount}
    </nav>
  );
}

export function WorkbenchHeader({
  title,
  subtitle,
  brandHref = '/',
  wrapBrand = true,
  className = 'top-nav',
  afterNavigation,
  ...navigation
}: NavigationProps & {
  title: ReactNode;
  subtitle?: ReactNode;
  brandHref?: string | null;
  wrapBrand?: boolean;
  className?: string;
  afterNavigation?: ReactNode;
}) {
  const copy = (
    <>
      <div className="brand-seal" aria-hidden="true">
        <BrandLogo rounded={false} />
      </div>
      <div className="brand-copy">
        <span className="brand-name">{title}</span>
        {subtitle ? <span className="brand-subtitle">{subtitle}</span> : null}
      </div>
    </>
  );
  const brand =
    brandHref === null ? (
      <div className="brand">{copy}</div>
    ) : (
      <Link className="brand brand-link" href={brandHref} onClick={navigation.onNavigate}>
        {copy}
      </Link>
    );
  return (
    <header className={className}>
      {wrapBrand ? <div className="workspace-nav-leading">{brand}</div> : brand}
      <WorkbenchNavigation {...navigation} />
      {afterNavigation}
    </header>
  );
}
