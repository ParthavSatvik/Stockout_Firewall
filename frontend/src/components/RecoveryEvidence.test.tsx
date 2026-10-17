import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecoveryEvidence } from './RecoveryEvidence';
import { api } from '../lib/api';
vi.mock('../lib/api', () => ({ api: { get: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><RecoveryEvidence orderId="order1" /></QueryClientProvider>);
}
test('shows confirmed and proposed separately with the baseline caveat', async () => {
  vi.mocked(api.get).mockResolvedValue({ plan_id: 'p', landed_cost: 4000, budget_headroom: 100,
    budget_respected: true, supplier_limit_respected: true, caveat: 'Planned coverage is not delivery.',
    items: [{ product: 'Rice', unit: 'kg', requested: 100, confirmed: 40, proposed: 60, delivered: 0,
      uncovered: 0, no_recovery_baseline: 40, additional_planned_coverage: 60 }] });
  show();
  expect(await screen.findByText('40 kg')).toBeTruthy();
  expect(screen.getByText('60 kg')).toBeTruthy();
  expect(screen.getByText('Planned coverage is not delivery.')).toBeTruthy();
});
test('shows a recoverable error instead of fabricated metrics', async () => {
  vi.mocked(api.get).mockRejectedValue(new Error('offline'));
  show();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
});
test('has no fabricated evidence before approval', async () => {
  vi.mocked(api.get).mockResolvedValue({ plan_id: null, items: [] });
  show();
  await vi.waitFor(() => expect(screen.queryByRole('status')).toBeNull());
  expect(screen.queryByText('Recovery evidence')).toBeNull();
});
