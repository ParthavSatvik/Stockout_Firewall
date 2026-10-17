import { useT } from "../lib/i18n";
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { formatINR } from '../lib/format';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';

type Evidence = {
  plan_id: string | null; reason: string; landed_cost: number; budget_headroom: number | null;
  budget_respected: boolean; supplier_limit_respected: boolean; caveat: string;
  items: { product: string; unit: string; requested: number; confirmed: number; proposed: number;
    delivered: number; uncovered: number; no_recovery_baseline: number | null; additional_planned_coverage: number | null }[];
};
export function RecoveryEvidence({ orderId }: { orderId: string }) {
  const { t } = useT();
  const query = useQuery({ queryKey: ['evidence', orderId], queryFn: () => api.get<Evidence>(`/api/orders/${orderId}/evidence`), refetchInterval: 4000 });
  if (query.isPending) return <p role="status">Loading recovery evidence…</p>;
  if (query.isError) return <p role="alert">{t("order.evidenceError")} <button onClick={() => query.refetch()}>{t("common.retry")}</button></p>;
  const data = query.data;
  if (!data.plan_id) return null;
  return <Card data-testid="recovery-evidence">
    <CardHeader><CardTitle>{t("order.evidence")}</CardTitle><p className="text-sm text-slate-500">{t("order.evidenceDesc")}</p></CardHeader>
    <CardContent className="space-y-4">
      <div className="flex flex-wrap gap-3 text-sm">
        <span>{data.budget_respected ? t('order.budgetOk') : t('order.budgetBad')}</span>
        <span>{data.supplier_limit_respected ? t('order.limitOk') : t('order.limitBad')}</span>
        <span>{t('order.landedCost', { v: formatINR(data.landed_cost) })}</span>
        {data.budget_headroom !== null && <span>{t('order.headroom', { v: formatINR(data.budget_headroom) })}</span>}
      </div>
      {data.items.map(row => <div key={row.product} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
        <h3 className="font-semibold">{row.product} · {t('order.requested', { qty: row.requested, unit: row.unit })}</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <div>{t('order.confirmed')}<p className="text-xl font-semibold">{row.confirmed} {row.unit}</p></div>
          <div>{t('order.proposed')}<p className="text-xl font-semibold">{row.proposed} {row.unit}</p></div>
          <div>{t('order.delivered')}<p className="text-xl font-semibold">{row.delivered} {row.unit}</p></div>
          <div>{t('order.uncovered')}<p className="text-xl font-semibold">{row.uncovered} {row.unit}</p></div>
        </div>
        {row.no_recovery_baseline !== null && <p className="mt-3 text-sm">Without replacement: {row.no_recovery_baseline} {row.unit} covered. Recovery adds {row.additional_planned_coverage} {row.unit} of planned coverage.</p>}
      </div>)}
      <p className="text-xs text-slate-500">{data.caveat}</p>
    </CardContent>
  </Card>;
}
