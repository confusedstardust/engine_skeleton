export type Product = { id: string; name: string; credits: number; price_fen: number; audience?: string; features?: string[]; billing_period?: string };

export type Order = { id: string; name: string; credits: number; payable_fen: number; status: string; fulfillment_status: string; payment_status: string; qr_ready: boolean; expires_at: string; billing_period?: string; credit_delivery?: string };
