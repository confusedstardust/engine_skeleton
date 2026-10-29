import type { ComponentPropsWithoutRef, ReactNode } from 'react';

type PricingCardProps = Omit<ComponentPropsWithoutRef<'article'>, 'title'> & {
  name: string;
  icon?: ReactNode;
  badge?: ReactNode;
  ribbon?: ReactNode;
  heading?: string;
  description?: string;
  action: ReactNode;
  price?: ReactNode;
  paymentCaption?: ReactNode;
  details?: ReactNode;
  variant?: 'plan' | 'resource';
};

export function PricingCard({ name, icon, badge, ribbon, heading, description, action, price, paymentCaption,
  details, variant = 'plan', className = '', children, ...props }: PricingCardProps) {
  return <article {...props} className={`pricing-card ${className}`}>
    {ribbon && <span className="pricing-ribbon">{ribbon}</span>}
    <div className="pricing-card-top">{icon}<h2 className="pricing-card-category pricing-card-name">{name}</h2>{badge}</div>
    {heading && <div className="pricing-plan-heading"><h3>{heading}</h3>{description && <p>{description}</p>}</div>}
    {children}
    {variant === 'plan' && action}
    {price}
    {paymentCaption !== undefined && <div className="pricing-payment-caption">{paymentCaption}</div>}
    {variant === 'resource' && action}
    {details}
  </article>;
}

export function PricingFeatures({ title, features, children }: { title: string; features: string[]; children?: ReactNode }) {
  return <div className="pricing-card-details"><h4 className="pricing-feature-heading">{title}</h4>
    <ul>{features.map((feature, index) => <li key={`${index}:${feature}`}>{feature}</li>)}</ul>{children}
  </div>;
}
